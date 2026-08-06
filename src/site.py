from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from .feeds import generate_feeds
from .models import Event
from .persistence import atomic_write_json, atomic_write_text


INDEX_HTML = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Aktuelle Capeet-Konzerte in Österreich, unabhängig aufbereitet und filterbar.">
<title>Capeet Gig Radar Österreich</title>
<link rel="alternate" type="application/rss+xml" title="Alle Neuigkeiten" href="feed.xml">
<link rel="stylesheet" href="assets/styles.css"><script src="assets/app.js" defer></script></head>
<body><a class="skip" href="#results">Zu den Ergebnissen</a>
<header><p class="eyebrow">Unabhängige Konzertübersicht</p><h1>Capeet Gig Radar Österreich</h1><p class="subtitle">Inoffizieller Filter und Neueinträge-Feed für die Capeet-Gigliste</p></header>
<main><section class="controls" aria-labelledby="filter-heading"><h2 id="filter-heading">Termine filtern</h2>
<label class="search">Volltextsuche <input id="search" type="search" placeholder="Künstler, Titel, Venue oder Ort" autocomplete="off"></label>
<fieldset><legend>Bundesländer</legend><div class="quick"><button type="button" data-states="all">Alle</button><button type="button" data-states="none">Keine</button><button type="button" data-states="vienna">Nur Wien</button></div><div id="states" class="checks"></div></fieldset>
<fieldset><legend>Genres</legend><div id="genres" class="checks"></div></fieldset>
<div class="options"><label><input id="cancelled" type="checkbox"> Abgesagte anzeigen</label><label><input id="changes" type="checkbox"> Nur neu/geändert</label>
<label>Sortierung <select id="sort"><option value="discovered-desc">Zuletzt bei Capeet entdeckt</option><option value="changed-desc">Zuletzt geändert</option><option value="date-asc">Konzertdatum aufsteigend</option><option value="date-desc">Konzertdatum absteigend</option></select></label><button id="reset" type="button">Zurücksetzen</button></div></section>
<p id="count" class="count" role="status" aria-live="polite">Termine werden geladen …</p><section id="results" class="cards" aria-label="Konzerte"></section>
<noscript>Die filterbare Liste benötigt JavaScript. Änderungen stehen auch im <a href="feed.xml">RSS-Feed</a>.</noscript></main>
<footer><p id="metadata">Datenstand wird geladen …</p><p class="feeds"><a href="feed.xml">RSS: alle Neuigkeiten</a></p><p id="selected-feeds" class="feeds" aria-label="RSS-Feeds der ausgewählten Bundesländer"></p>
<p>Quelle: <a href="https://www.capeet.com/gigs_list.html" rel="noopener noreferrer">Original-Gigliste von Capeet</a>. Unabhängiges Projekt, keine offizielle Capeet-Seite. Angaben ohne Gewähr.</p></footer></body></html>
"""


STYLES_CSS = """:root{--bg:#f4f0e8;--paper:#fffdf8;--ink:#17201b;--muted:#59645d;--green:#176b4d;--gold:#d99b27;--red:#a62b2b;--line:#cbd2cb;color-scheme:light}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:1rem/1.5 system-ui,-apple-system,sans-serif}header,main,footer{width:min(76rem,calc(100% - 2rem));margin:auto}header{padding:3.5rem 0 2rem}h1{font-size:clamp(2.6rem,7vw,5.4rem);line-height:.95;margin:.1em 0}.eyebrow{color:var(--green);font-weight:800;letter-spacing:.1em;text-transform:uppercase}.subtitle{font-size:1.2rem}.skip{position:absolute;left:-9999px}.skip:focus{left:1rem;top:1rem;background:white;padding:.7rem;z-index:9}.controls{background:var(--paper);border:1px solid var(--line);border-radius:1rem;padding:1rem;display:grid;gap:1rem}.controls h2{margin:0}.search{display:grid;gap:.25rem}input[type=search],select,button{font:inherit;border:1px solid #7f8d84;border-radius:.4rem;background:white;color:inherit;padding:.55rem}.checks{display:flex;flex-wrap:wrap;gap:.35rem 1rem}.checks label,.options label{white-space:nowrap}.quick,.options{display:flex;flex-wrap:wrap;align-items:end;gap:.6rem}.quick{margin-bottom:.6rem}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,20rem),1fr));gap:1rem}.card{background:var(--paper);border:1px solid var(--line);border-radius:.8rem;padding:1rem}.card.cancelled{border-color:var(--red)}.date{font-weight:800;color:var(--green)}.card h2{font-size:1.35rem;margin:.25rem 0}.title,.place,.source{color:var(--muted)}.badges,.links{display:flex;flex-wrap:wrap;gap:.35rem}.badge{background:#e1ebe5;border-radius:99px;padding:.12rem .5rem;font-size:.82rem}.badge.alert{background:#f5d7d4;color:#741c1c}.badge.change{background:#fff0c8}.count{font-weight:700;margin:1.2rem 0}a{color:#075d43;text-underline-offset:.18em}footer{border-top:1px solid var(--line);margin-top:3rem;padding:2rem 0;color:var(--muted)}:focus-visible{outline:3px solid var(--gold);outline-offset:2px}@media(max-width:600px){header{padding-top:2rem}}"""


APP_JS = r"""'use strict';
const STATES=['Burgenland','Kärnten','Niederösterreich','Oberösterreich','Salzburg','Steiermark','Tirol','Vorarlberg','Wien','Unbekannt'];
const byId=id=>document.getElementById(id);const list=byId('results'),count=byId('count'),search=byId('search'),cancelled=byId('cancelled'),changes=byId('changes'),sort=byId('sort');let events=[];
function node(tag,className,text){const item=document.createElement(tag);if(className)item.className=className;if(text!==undefined)item.textContent=text;return item}
function safeLink(url){try{const parsed=new URL(url,location.href);return ['http:','https:'].includes(parsed.protocol)?parsed.href:null}catch{return null}}
function checkbox(container,value,checked){const label=node('label');const input=node('input');input.type='checkbox';input.value=value;input.checked=checked;label.append(input,document.createTextNode(` ${value}`));container.append(label)}
function selected(selector){return new Set([...document.querySelectorAll(selector)].filter(item=>item.checked).map(item=>item.value))}
function slug(value){return value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('de').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')}
function updateFeeds(states){const target=byId('selected-feeds');target.replaceChildren(document.createTextNode('Ausgewählte Feeds: '));[...states].filter(value=>value!=='Unbekannt').forEach((value,index)=>{if(index)target.append(document.createTextNode(' · '));const link=node('a','',value);link.href=`feeds/neu-${slug(value)}.xml`;target.append(link)})}
function isChanged(event){return Boolean(event.changed_at)&&!event.baseline}
function save(){const state={q:search.value,states:[...selected('#states input')],genres:[...selected('#genres input')],cancelled:cancelled.checked,changes:changes.checked,sort:sort.value};localStorage.setItem('capeet-filters',JSON.stringify(state));const params=new URLSearchParams();if(state.q)params.set('q',state.q);if(state.states.length!==1||state.states[0]!=='Wien')params.set('states',state.states.join(','));if(state.genres.length)params.set('genres',state.genres.join(','));if(state.cancelled)params.set('cancelled','1');if(state.changes)params.set('changed','1');if(state.sort!=='discovered-desc')params.set('sort',state.sort);history.replaceState(null,'',`${location.pathname}${params.size?'?'+params:''}`)}
function card(event){const article=node('article',`card ${event.status==='cancelled'?'cancelled':''}`);article.append(node('p','date',new Intl.DateTimeFormat('de-AT',{weekday:'short',day:'2-digit',month:'2-digit',year:'numeric'}).format(new Date(`${event.event_date}T12:00:00`))));const heading=node('h2');event.artists.forEach((artist,index)=>{if(index)heading.append(document.createTextNode(' · '));const href=safeLink(artist.link);if(href){const link=node('a','',artist.name);link.href=href;link.rel='noopener noreferrer';heading.append(link)}else heading.append(document.createTextNode(artist.name));if(artist.country)heading.append(document.createTextNode(` (${artist.country})`))});article.append(heading);if(event.title)article.append(node('p','title',event.title));article.append(node('p','place',`${event.venue} · ${event.postal_code?event.postal_code+' ':''}${event.city}`));const badges=node('p','badges');badges.append(node('span','badge',event.state),node('span','badge',event.genre.family));event.genre.subgenres.forEach(value=>badges.append(node('span','badge',value)));if(event.status==='cancelled')badges.append(node('span','badge alert','Abgesagt'));if(event.status==='postponed')badges.append(node('span','badge alert','Verschoben'));if(!event.active)badges.append(node('span','badge alert','Nicht mehr gelistet'));if(isChanged(event))badges.append(node('span','badge change',event.revision===1?'Neu':'Geändert'));article.append(badges);article.append(node('p','source',`Entdeckt am: ${event.first_seen_at?new Intl.DateTimeFormat('de-AT',{dateStyle:'medium'}).format(new Date(event.first_seen_at)):'–'} · Geändert am: ${event.changed_at?new Intl.DateTimeFormat('de-AT',{dateStyle:'medium'}).format(new Date(event.changed_at)):'–'}`));const links=node('p','links');event.links.forEach(item=>{const href=safeLink(item.url);if(!href)return;const link=node('a','',item.label);link.href=href;link.rel='noopener noreferrer';links.append(link)});const source=node('a','','Capeet-Quellseite');source.href='https://www.capeet.com/gigs_list.html';source.rel='noopener noreferrer';links.append(source);article.append(links);return article}
function render(){const stateSet=selected('#states input'),genreSet=selected('#genres input'),query=search.value.trim().toLocaleLowerCase('de');let visible=events.filter(event=>{const words=[event.title,event.venue,event.city,event.source_text,...event.artists.map(item=>item.name)].join(' ').toLocaleLowerCase('de');return stateSet.has(event.state)&&(!genreSet.size||genreSet.has(event.genre.family))&&(!query||words.includes(query))&&(cancelled.checked||event.status!=='cancelled')&&(!changes.checked||isChanged(event))});const compare={'discovered-desc':(a,b)=>(b.first_seen_at||'').localeCompare(a.first_seen_at||''),'changed-desc':(a,b)=>(b.changed_at||'').localeCompare(a.changed_at||''),'date-asc':(a,b)=>a.event_date.localeCompare(b.event_date),'date-desc':(a,b)=>b.event_date.localeCompare(a.event_date)}[sort.value];visible.sort(compare);list.replaceChildren(...visible.map(card));count.textContent=`${visible.length} ${visible.length===1?'Termin':'Termine'} angezeigt`;updateFeeds(stateSet);save()}
function restore(){let saved={};try{saved=JSON.parse(localStorage.getItem('capeet-filters')||'{}')}catch{}const params=new URLSearchParams(location.search);search.value=params.get('q')??saved.q??'';cancelled.checked=params.has('cancelled')||Boolean(saved.cancelled);changes.checked=params.has('changed')||Boolean(saved.changes);sort.value=params.get('sort')||saved.sort||'discovered-desc';const requested=params.has('states')?(params.get('states')||'').split(','):(saved.states||['Wien']);document.querySelectorAll('#states input').forEach(item=>item.checked=requested.includes(item.value));const genres=params.has('genres')?(params.get('genres')||'').split(','):(saved.genres||[]);document.querySelectorAll('#genres input').forEach(item=>item.checked=genres.includes(item.value))}
async function start(){try{const response=await fetch('data/gigs.json');if(!response.ok)throw new Error('HTTP');const payload=await response.json();events=payload.events;STATES.forEach(value=>checkbox(byId('states'),value,value==='Wien'));[...new Set(events.map(item=>item.genre.family))].sort((a,b)=>a.localeCompare(b,'de')).forEach(value=>checkbox(byId('genres'),value,false));restore();byId('metadata').textContent=`Generiert: ${new Intl.DateTimeFormat('de-AT',{dateStyle:'medium',timeStyle:'short'}).format(new Date(payload.generated_at))} · Quelle abgerufen: ${new Intl.DateTimeFormat('de-AT',{dateStyle:'medium',timeStyle:'short'}).format(new Date(payload.source_checked_at))} · ${events.length} gespeicherte Termine`;render()}catch{count.textContent='Die Konzertdaten konnten nicht geladen werden.'}}
document.addEventListener('input',event=>{if(event.target.closest('.controls'))render()});document.querySelectorAll('[data-states]').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('#states input').forEach(item=>item.checked=button.dataset.states==='all'||(button.dataset.states==='vienna'&&item.value==='Wien'));render()}));byId('reset').addEventListener('click',()=>{search.value='';cancelled.checked=false;changes.checked=false;sort.value='discovered-desc';document.querySelectorAll('#states input').forEach(item=>item.checked=item.value==='Wien');document.querySelectorAll('#genres input').forEach(item=>item.checked=false);render()});start();
"""


def generate_site(events: list[Event], revisions: list[dict], output_dir: Path, site_url: str, generated_at: datetime, *, feed_limit: int = 100, feed_days: int = 90) -> None:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    backup = output_dir.with_name(f".{output_dir.name}.previous")
    try:
        atomic_write_text(staging / "index.html", INDEX_HTML)
        atomic_write_text(staging / "assets/styles.css", STYLES_CSS)
        atomic_write_text(staging / "assets/app.js", APP_JS)
        atomic_write_json(staging / "data/gigs.json", {"generated_at": generated_at.isoformat(), "source_checked_at": generated_at.isoformat(), "source_url": "https://www.capeet.com/gigs_list.html", "events": [event.to_dict() for event in events]})
        atomic_write_text(staging / ".nojekyll", "")
        generate_feeds(revisions, staging, site_url, generated_at, limit=feed_limit, days=feed_days)
        if backup.exists():
            shutil.rmtree(backup)
        if output_dir.exists():
            os.replace(output_dir, backup)
        os.replace(staging, output_dir)
        if backup.exists():
            shutil.rmtree(backup)
    except BaseException:
        if not output_dir.exists() and backup.exists():
            os.replace(backup, output_dir)
        shutil.rmtree(staging, ignore_errors=True)
        raise
