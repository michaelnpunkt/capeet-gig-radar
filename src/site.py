from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from .changelog import generate_changelog
from .feeds import generate_feeds
from .models import Event
from .persistence import atomic_write_json, atomic_write_text


INDEX_HTML = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Aktuelle Capeet-Konzerte in Österreich, unabhängig aufbereitet und filterbar.">
<title>Mosh Pit Crew Gig Radar</title>
<link rel="alternate" type="application/rss+xml" title="Alle Neuigkeiten" href="feed.xml">
<link rel="stylesheet" href="assets/styles.css"><script src="assets/app.js" defer></script></head>
<body id="top"><a class="skip" href="#results">Zu den Ergebnissen</a>
<header class="hero"><p class="eyebrow">Austria's underground radar</p><h1>Mosh Pit Crew<br><span>Gig Radar</span></h1><p class="subtitle">Punk, Hardcore, Metal &amp; mehr — gefiltert aus der Capeet-Gigliste.</p>
<aside class="capeet-shout" aria-label="Danke an Capeet"><strong>Big shout-out to <a href="https://www.capeet.com/gigs_list.html" rel="noopener noreferrer">Capeet</a></strong><span>für die seit Jahren gepflegte österreichische Gigliste. Diese inoffizielle Ansicht macht sie nur leichter durchsuchbar. Die Quelle wird bewusst nur einmal täglich abgerufen.</span><a class="capeet-cta" href="https://www.capeet.com/gigs_list.html" rel="noopener noreferrer">Original-Gigliste bei Capeet öffnen →</a></aside>
<nav class="status-bar" aria-label="Datenstand und Feeds"><span id="header-metadata">Datenstand wird geladen …</span><span class="nav-break" aria-hidden="true"></span><span title="Die öffentliche Capeet-Seite wird einmal pro Tag abgefragt; zwischendurch bleibt der zuletzt erfolgreiche Stand online.">Abruf: 1× täglich</span><a href="changes.html">Changelog</a><a href="https://www.capeet.com/gigs_list.html" rel="noopener noreferrer">Capeet Original</a><a href="feed.xml">Gesamt-RSS</a><details class="feed-menu"><summary>Bundesland-RSS</summary><div><a href="feeds/neu-burgenland.xml">Burgenland</a><a href="feeds/neu-karnten.xml">Kärnten</a><a href="feeds/neu-niederosterreich.xml">Niederösterreich</a><a href="feeds/neu-oberosterreich.xml">Oberösterreich</a><a href="feeds/neu-salzburg.xml">Salzburg</a><a href="feeds/neu-steiermark.xml">Steiermark</a><a href="feeds/neu-tirol.xml">Tirol</a><a href="feeds/neu-vorarlberg.xml">Vorarlberg</a><a href="feeds/neu-wien.xml">Wien</a></div></details></nav></header>
<main><section class="controls" aria-labelledby="filter-heading"><h2 id="filter-heading">Termine filtern</h2>
<label class="search">Volltextsuche <input id="search" type="search" placeholder="Künstler, Titel, Venue oder Ort" autocomplete="off"></label>
<fieldset><legend>Bundesländer</legend><div class="quick"><button type="button" data-states="all">Alle</button><button type="button" data-states="none">Keine</button></div><div id="states" class="checks"></div></fieldset>
<fieldset><legend>Genres</legend><div class="quick"><button type="button" data-genres="all">Alle</button><button type="button" data-genres="none">Keine</button></div><div id="genres" class="checks"></div></fieldset>
<fieldset class="time-filters"><legend>Zeitraum <button class="help" type="button" title="Monat und kommende Tage können kombiniert werden. Alle Monate beziehungsweise alle kommenden Termine deaktiviert den jeweiligen Teilfilter." aria-label="Hilfe zum Zeitraumfilter">?</button></legend><label>Monat <select id="month"><option value="">Alle Monate</option></select></label><label>Kommende Tage <select id="days"><option value="">Alle kommenden Termine</option><option value="7">7 Tage</option><option value="14">14 Tage</option><option value="30">30 Tage</option><option value="60">60 Tage</option><option value="90">90 Tage</option></select></label></fieldset>
<div class="options"><label><input id="past" type="checkbox" checked> Vergangene Gigs ausblenden</label><label><input id="cancelled" type="checkbox" checked> Abgesagte Gigs ausblenden</label><label><input id="changes" type="checkbox"> Nur neu/geändert <button class="help" type="button" title="Zeigt echte Neueinträge sowie Events, deren Line-up, Venue, Ort, Links oder Status später geändert wurden." aria-label="Erklärung zu neu und geändert">?</button></label>
<label>Sortierung <select id="sort" aria-describedby="sort-help"><option value="discovered-desc">Zuletzt bei Capeet entdeckt</option><option value="changed-desc">Zuletzt geändert</option><option value="date-asc">Konzertdatum aufsteigend</option><option value="date-desc">Konzertdatum absteigend</option></select></label><span id="sort-help" class="hint">„Capeet entdeckt“ = erstmals von diesem Radar gesehen. „Zuletzt geändert“ = jüngste erkannte Revision.</span><button id="reset" type="button">Zurücksetzen</button></div></section>
<div class="results-toolbar"><p id="count" class="count" role="status" aria-live="polite">Termine werden geladen …</p><div class="view-toggle" role="group" aria-label="Darstellung"><button type="button" data-view="grid" aria-pressed="true">Kacheln</button><button type="button" data-view="list" aria-pressed="false">Liste</button></div></div><section id="results" class="cards" aria-label="Konzerte"></section>
<noscript>Die filterbare Liste benötigt JavaScript. Änderungen stehen auch im <a href="feed.xml">RSS-Feed</a>.</noscript></main>
<a class="back-top" href="#top" aria-label="Zurück zum Seitenanfang">↑ Nach oben</a><footer><p id="metadata">Datenstand wird geladen …</p><p class="feeds"><a href="changes.html">Alle Änderungen ansehen</a> · <a href="feed.xml">RSS: alle Neuigkeiten</a></p>
<p class="contact-links"><strong>Feedback &amp; Kontakt:</strong> <a href="https://github.com/michaelnpunkt/capeet-gig-radar/issues/new?template=bug_report.yml">Fehler melden</a> · <a href="https://github.com/michaelnpunkt/capeet-gig-radar/issues/new?template=feature_request.yml">Idee vorschlagen</a> · <a href="https://github.com/michaelnpunkt/capeet-gig-radar/issues/new/choose">Sonstiges Feedback</a> · <a href="https://github.com/michaelnpunkt/capeet-gig-radar">Quellcode</a></p>
<p>Quelle: <a href="https://www.capeet.com/gigs_list.html" rel="noopener noreferrer">Original-Gigliste von Capeet</a>. Unabhängiges Projekt, keine offizielle Capeet-Seite. Angaben ohne Gewähr.</p></footer></body></html>
"""


STYLES_CSS = (Path(__file__).resolve().parents[1] / "docs" / "assets" / "styles.css").read_text(encoding="utf-8").split(".event-changes{", 1)[0] + ".event-changes{position:relative;z-index:1;margin:.7rem 0;padding:.65rem .75rem;background:#251116;border-left:3px solid var(--blood)}.event-changes-title{margin:0 0 .3rem;color:#ff9baa;font-size:.78rem;font-weight:900;text-transform:uppercase}.event-change{margin:.2rem 0;font-size:.88rem}.event-change del,.change-details del{color:#ff9baa;text-decoration-thickness:2px}.event-change ins,.change-details ins{color:var(--acid);font-weight:800;text-decoration:none}.list-view .event-changes{grid-column:2/5;margin:.35rem 0}.list-view .source{grid-column:2/4}.nav-break{flex-basis:100%;height:0}"


APP_JS = r"""'use strict';
const STATES=['Burgenland','Kärnten','Niederösterreich','Oberösterreich','Salzburg','Steiermark','Tirol','Vorarlberg','Wien','Unbekannt'];
const byId=id=>document.getElementById(id);const list=byId('results'),count=byId('count'),search=byId('search'),past=byId('past'),cancelled=byId('cancelled'),changes=byId('changes'),sort=byId('sort'),month=byId('month'),days=byId('days'),viewButtons=[...document.querySelectorAll('[data-view]')];let events=[],viewMode='grid';
function node(tag,className,text){const item=document.createElement(tag);if(className)item.className=className;if(text!==undefined)item.textContent=text;return item}
function safeLink(url){try{const parsed=new URL(url,location.href);return ['http:','https:'].includes(parsed.protocol)?parsed.href:null}catch{return null}}
function checkbox(container,value,checked){const label=node('label');const input=node('input');input.type='checkbox';input.value=value;input.checked=checked;label.append(input,document.createTextNode(` ${value}`));container.append(label)}
function selected(selector){return new Set([...document.querySelectorAll(selector)].filter(item=>item.checked).map(item=>item.value))}
function isChanged(event){return Boolean(event.changed_at)}
function setView(value){viewMode=value==='list'?'list':'grid';list.classList.toggle('list-view',viewMode==='list');viewButtons.forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.view===viewMode)))}
function save(){const genreInputs=[...document.querySelectorAll('#genres input')],state={filterVersion:2,q:search.value,states:[...selected('#states input')],genres:[...selected('#genres input')],month:month.value,days:days.value,past:past.checked,hideCancelled:cancelled.checked,changes:changes.checked,sort:sort.value,view:viewMode};localStorage.setItem('capeet-filters',JSON.stringify(state));const params=new URLSearchParams();if(state.q)params.set('q',state.q);if(state.states.length!==1||state.states[0]!=='Wien')params.set('states',state.states.join(','));if(state.genres.length!==genreInputs.length)params.set('genres',state.genres.join(','));if(state.month)params.set('month',state.month);if(state.days)params.set('days',state.days);if(!state.past)params.set('past','0');if(!state.hideCancelled)params.set('hide_cancelled','0');if(state.changes)params.set('changed','1');if(state.sort!=='discovered-desc')params.set('sort',state.sort);if(state.view==='list')params.set('view','list');history.replaceState(null,'',`${location.pathname}${params.size?'?'+params:''}`)}
function displayChange(field,value){if(value===null||value===undefined||value==='')return '–';if(field==='artists')return value.map(item=>item.name).join(' · ');if(field==='event_date')return new Intl.DateTimeFormat('de-AT',{day:'2-digit',month:'2-digit',year:'numeric'}).format(new Date(`${value}T12:00:00`));if(field==='status')return {scheduled:'angekündigt',cancelled:'abgesagt',postponed:'verschoben'}[value]||value;if(field==='active')return value?'gelistet':'nicht gelistet';return String(value)}
function changeRow(field,values){const labels={artists:'Line-up',event_date:'Datum',title:'Titel',venue:'Venue',city:'Ort',postal_code:'PLZ',status:'Eventstatus',active:'Listung'},row=node('p','event-change'),label=node('strong','',`${labels[field]||field}: `);row.append(label);if(field==='artists'){const before=values.from.map(item=>item.name),after=values.to.map(item=>item.name),removed=before.filter(name=>!after.includes(name)),added=after.filter(name=>!before.includes(name));if(removed.length){row.append(node('del','',removed.join(' · ')),document.createTextNode(' entfällt'))}if(removed.length&&added.length)row.append(document.createTextNode(' · '));if(added.length){row.append(node('ins','',added.join(' · ')),document.createTextNode(' neu'))}if(!removed.length&&!added.length)row.append(node('del','',displayChange(field,values.from)),document.createTextNode(' → '),node('ins','',displayChange(field,values.to)))}else row.append(node('del','',displayChange(field,values.from)),document.createTextNode(' → '),node('ins','',displayChange(field,values.to)));return row}
function revisionDetails(event){const changes=event.latest_revision?.changes||{},fields=['artists','event_date','title','venue','city','postal_code','status','active'].filter(field=>changes[field]);if(!fields.length)return null;const section=node('div','event-changes');section.append(node('p','event-changes-title','Erkannte Änderung'));fields.forEach(field=>section.append(changeRow(field,changes[field])));return section}
function card(event){const article=node('article',`card ${event.status==='cancelled'?'cancelled':''}`);article.append(node('p','date',new Intl.DateTimeFormat('de-AT',{weekday:'short',day:'2-digit',month:'2-digit',year:'numeric'}).format(new Date(`${event.event_date}T12:00:00`))));const heading=node('h2');event.artists.forEach((artist,index)=>{if(index)heading.append(document.createTextNode(' · '));const href=safeLink(artist.link);if(href){const link=node('a','',artist.name);link.href=href;link.rel='noopener noreferrer';heading.append(link)}else heading.append(document.createTextNode(artist.name));if(artist.country)heading.append(document.createTextNode(` (${artist.country})`))});article.append(heading);if(event.title)article.append(node('p','title',event.title));article.append(node('p','place',`${event.venue} · ${event.postal_code?event.postal_code+' ':''}${event.city}`));const badges=node('p','badges');badges.append(node('span','badge',event.state),node('span','badge',event.genre.family));event.genre.subgenres.forEach(value=>badges.append(node('span','badge',value)));if(event.status==='cancelled')badges.append(node('span','badge alert','Event abgesagt'));if(event.status==='postponed')badges.append(node('span','badge alert','Event verschoben'));if(!event.active)badges.append(node('span','badge alert','Nicht mehr gelistet'));if(isChanged(event))badges.append(node('span','badge change',event.revision===1?'Neu':'Geändert'));article.append(badges);const details=revisionDetails(event);if(details)article.append(details);article.append(node('p','source',`Entdeckt am: ${event.first_seen_at?new Intl.DateTimeFormat('de-AT',{dateStyle:'medium'}).format(new Date(event.first_seen_at)):'–'} · Geändert am: ${event.changed_at?new Intl.DateTimeFormat('de-AT',{dateStyle:'medium'}).format(new Date(event.changed_at)):'–'}`));const links=node('p','links');event.links.forEach(item=>{const href=safeLink(item.url);if(!href)return;const link=node('a','',item.label);link.href=href;link.rel='noopener noreferrer';links.append(link)});const source=node('a','','Capeet-Quellseite');source.href='https://www.capeet.com/gigs_list.html';source.rel='noopener noreferrer';links.append(source);article.append(links);return article}
function render(){const stateSet=selected('#states input'),genreSet=selected('#genres input'),query=search.value.trim().toLocaleLowerCase('de'),today=new Date(),start=new Date(today.getFullYear(),today.getMonth(),today.getDate()),limit=days.value?new Date(today.getFullYear(),today.getMonth(),today.getDate()+Number(days.value)):null;let visible=events.filter(event=>{const words=[event.title,event.venue,event.city,event.source_text,...event.artists.map(item=>item.name)].join(' ').toLocaleLowerCase('de'),date=new Date(`${event.event_date}T12:00:00`),monthMatch=!month.value||event.event_date.slice(0,7)===month.value,daysMatch=!limit||(date>=start&&date<=limit),pastMatch=!past.checked||date>=start;return stateSet.has(event.state)&&genreSet.has(event.genre.family)&&monthMatch&&daysMatch&&pastMatch&&(!query||words.includes(query))&&(!cancelled.checked||event.status!=='cancelled')&&(!changes.checked||isChanged(event))});const compare={'discovered-desc':(a,b)=>(b.first_seen_at||'').localeCompare(a.first_seen_at||''),'changed-desc':(a,b)=>(b.changed_at||'').localeCompare(a.changed_at||''),'date-asc':(a,b)=>a.event_date.localeCompare(b.event_date),'date-desc':(a,b)=>b.event_date.localeCompare(a.event_date)}[sort.value];visible.sort(compare);list.replaceChildren(...visible.map(card));count.textContent=`${visible.length} ${visible.length===1?'Termin':'Termine'} angezeigt`;save()}
function restore(){let saved={};try{saved=JSON.parse(localStorage.getItem('capeet-filters')||'{}')}catch{}const params=new URLSearchParams(location.search),genreInputs=[...document.querySelectorAll('#genres input')];search.value=params.get('q')??saved.q??'';month.value=params.get('month')??saved.month??'';days.value=params.get('days')??saved.days??'';past.checked=params.has('past')?params.get('past')!=='0':saved.past??true;cancelled.checked=params.has('hide_cancelled')?params.get('hide_cancelled')!=='0':saved.filterVersion===2?saved.hideCancelled??true:true;changes.checked=params.has('changed')||Boolean(saved.changes);sort.value=params.get('sort')||saved.sort||'discovered-desc';setView(params.get('view')||saved.view||'grid');const requested=params.has('states')?(params.get('states')||'').split(','):(saved.states||['Wien']);document.querySelectorAll('#states input').forEach(item=>item.checked=requested.includes(item.value));const genres=params.has('genres')?(params.get('genres')||'').split(','):saved.filterVersion===2?(saved.genres||[]):genreInputs.map(item=>item.value);genreInputs.forEach(item=>item.checked=genres.includes(item.value))}
async function start(){try{const [response,statusResponse]=await Promise.all([fetch('data/gigs.json'),fetch('data/status.json')]);if(!response.ok||!statusResponse.ok)throw new Error('HTTP');const payload=await response.json(),statusPayload=await statusResponse.json(),formatter=new Intl.DateTimeFormat('de-AT',{dateStyle:'medium',timeStyle:'short'});events=payload.events;STATES.forEach(value=>checkbox(byId('states'),value,value==='Wien'));[...new Set(events.map(item=>item.genre.family))].sort((a,b)=>a.localeCompare(b,'de')).forEach(value=>checkbox(byId('genres'),value,true));[...new Set(events.map(item=>item.event_date.slice(0,7)))].sort().forEach(value=>{const option=node('option','',new Intl.DateTimeFormat('de-AT',{month:'long',year:'numeric'}).format(new Date(`${value}-01T12:00:00`)));option.value=value;month.append(option)});restore();const checked=`Zuletzt geprüft: ${formatter.format(new Date(statusPayload.checked_at))}`,changed=`Daten geändert: ${formatter.format(new Date(statusPayload.changed_at))}`;byId('header-metadata').textContent=`${checked} · ${changed} · ${events.length} Gigs`;byId('metadata').textContent=`${checked} · ${changed} · ${events.length} Gigs`;render()}catch{count.textContent='Die Konzertdaten konnten nicht geladen werden.'}}
document.addEventListener('input',event=>{if(event.target.closest('.controls'))render()});document.querySelectorAll('[data-states]').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('#states input').forEach(item=>item.checked=button.dataset.states==='all');render()}));document.querySelectorAll('[data-genres]').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('#genres input').forEach(item=>item.checked=button.dataset.genres==='all');render()}));viewButtons.forEach(button=>button.addEventListener('click',()=>{setView(button.dataset.view);save()}));byId('reset').addEventListener('click',()=>{search.value='';month.value='';days.value='';past.checked=true;cancelled.checked=true;changes.checked=false;sort.value='discovered-desc';setView('grid');document.querySelectorAll('#states input').forEach(item=>item.checked=item.value==='Wien');document.querySelectorAll('#genres input').forEach(item=>item.checked=true);render()});start();
"""


def generate_site(
    events: list[Event],
    revisions: list[dict],
    output_dir: Path,
    site_url: str,
    generated_at: datetime,
    *,
    source_checked_at: datetime | None = None,
    source_changed_at: datetime | None = None,
    source_changed: bool = True,
    feed_limit: int = 100,
    feed_days: int = 90,
) -> None:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    backup = output_dir.with_name(f".{output_dir.name}.previous")
    try:
        latest_revisions: dict[str, dict] = {}
        for revision in sorted(revisions, key=lambda item: (item.get("detected_at", ""), item.get("revision", 0))):
            latest_revisions[str(revision.get("event_id", ""))] = revision
        event_data = []
        for event in events:
            value = event.to_dict()
            latest = latest_revisions.get(event.id)
            value["latest_revision"] = {
                "kind": latest.get("kind"),
                "detected_at": latest.get("detected_at"),
                "changes": latest.get("changes", {}),
            } if latest else None
            event_data.append(value)
        atomic_write_text(staging / "index.html", INDEX_HTML)
        atomic_write_text(staging / "assets/styles.css", STYLES_CSS)
        atomic_write_text(staging / "assets/app.js", APP_JS)
        checked_at = source_checked_at or generated_at
        changed_at = source_changed_at or generated_at
        atomic_write_json(staging / "data/gigs.json", {"generated_at": generated_at.isoformat(), "source_checked_at": checked_at.isoformat(), "source_url": "https://www.capeet.com/gigs_list.html", "events": event_data})
        atomic_write_json(staging / "data/status.json", {"checked_at": checked_at.isoformat(), "changed_at": changed_at.isoformat(), "source_url": "https://www.capeet.com/gigs_list.html", "source_changed": source_changed})
        generate_changelog(revisions, staging, generated_at)
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
