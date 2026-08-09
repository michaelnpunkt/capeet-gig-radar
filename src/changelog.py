from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .persistence import atomic_write_json, atomic_write_text


CHANGE_LABELS = {
    "new": "Neu",
    "changed": "Geändert",
    "cancelled": "Abgesagt",
    "postponed": "Verschoben",
    "reactivated": "Wieder gelistet",
    "unlisted": "Nicht mehr gelistet",
}

FIELD_LABELS = {
    "event_date": "Konzertdatum",
    "artists": "Line-up",
    "title": "Titel",
    "venue": "Venue",
    "city": "Ort",
    "state": "Bundesland",
    "postal_code": "Postleitzahl",
    "status": "Status",
    "links": "Links",
    "active": "Listung",
}


def revision_type(revision: dict[str, Any]) -> str:
    kind = str(revision.get("kind", "changed"))
    if kind != "changed":
        return kind
    changes = revision.get("changes", {})
    active = changes.get("active", {})
    if active.get("from") is False and active.get("to") is True:
        return "reactivated"
    status = changes.get("status", {})
    if status.get("to") == "cancelled":
        return "cancelled"
    if status.get("to") == "postponed":
        return "postponed"
    return "changed"


def revision_anchor(revision: dict[str, Any]) -> str:
    event = revision.get("event", {})
    return f"change-{event.get('id', 'unknown')}-{revision.get('revision', 0)}"


def changelog_revisions(revisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for revision in revisions:
        if revision.get("kind") not in {"new", "changed", "unlisted"}:
            continue
        item = dict(revision)
        item["display_type"] = revision_type(revision)
        item["anchor"] = revision_anchor(revision)
        result.append(item)
    return sorted(
        result,
        key=lambda value: (value.get("detected_at", ""), value.get("revision", 0)),
        reverse=True,
    )


CHANGELOG_HTML = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Chronik neuer, geänderter und nicht mehr gelisteter Capeet-Konzerte.">
<title>Änderungen · Mosh Pit Crew Gig Radar</title>
<link rel="alternate" type="application/rss+xml" title="Alle Neuigkeiten" href="feed.xml">
<link rel="stylesheet" href="assets/styles.css"><script src="assets/changes.js" defer></script></head>
<body id="top"><a class="skip" href="#changes-results">Zu den Änderungen</a>
<header class="hero compact"><p class="eyebrow">Was hat sich getan?</p><h1>Gig<br><span>Changelog</span></h1><p class="subtitle">Neue, geänderte, abgesagte und nicht mehr gelistete Termine — chronologisch seit dem letzten erfolgreichen Tageslauf.</p>
<nav class="status-bar" aria-label="Seitennavigation"><a href="index.html">← Alle Gigs</a><a href="feed.xml">Gesamt-RSS</a><span id="changes-metadata">Änderungen werden geladen …</span></nav></header>
<main><section class="controls change-controls" aria-labelledby="filter-heading"><h2 id="filter-heading">Änderungen filtern</h2>
<label>Zeitraum <select id="change-days"><option value="7">Letzte 7 Tage</option><option value="30">Letzte 30 Tage</option><option value="90" selected>Letzte 90 Tage</option><option value="all">Gesamte Historie</option></select></label>
<label>Bundesland <select id="change-state"><option value="">Alle Bundesländer</option></select></label>
<label>Änderung <select id="change-type"><option value="">Alle Änderungen</option><option value="new">Neu</option><option value="changed">Geändert</option><option value="cancelled">Abgesagt</option><option value="postponed">Verschoben</option><option value="reactivated">Wieder gelistet</option><option value="unlisted">Nicht mehr gelistet</option></select></label>
</section><p id="change-count" class="count" role="status" aria-live="polite">Änderungen werden geladen …</p><div id="changes-results" class="change-days" aria-label="Änderungschronik"></div>
<noscript>Die filterbare Chronik benötigt JavaScript. Alle Neuigkeiten stehen auch im <a href="feed.xml">RSS-Feed</a>.</noscript></main>
<a class="back-top" href="#top" aria-label="Zurück zum Seitenanfang">↑ Nach oben</a><footer><p>Revisionen bleiben bis zu 730 Tage erhalten. Der RSS-Feed enthält höchstens 100 Einträge der letzten 90 Tage.</p><p class="contact-links"><strong>Feedback &amp; Kontakt:</strong> <a href="https://github.com/michaelnpunkt/capeet-gig-radar/issues/new?template=bug_report.yml">Fehler melden</a> · <a href="https://github.com/michaelnpunkt/capeet-gig-radar/issues/new?template=feature_request.yml">Idee vorschlagen</a> · <a href="https://github.com/michaelnpunkt/capeet-gig-radar/issues">Offene Meldungen</a> · <a href="https://github.com/michaelnpunkt/capeet-gig-radar">Quellcode</a></p><p>Quelle: <a href="https://www.capeet.com/gigs_list.html" rel="noopener noreferrer">Original-Gigliste von Capeet</a>. Unabhängiges Projekt, Angaben ohne Gewähr.</p></footer></body></html>
"""


CHANGELOG_JS = r"""'use strict';
const LABELS={new:'Neu',changed:'Geändert',cancelled:'Abgesagt',postponed:'Verschoben',reactivated:'Wieder gelistet',unlisted:'Nicht mehr gelistet'};
const FIELDS={event_date:'Konzertdatum',artists:'Line-up',title:'Titel',venue:'Venue',city:'Ort',state:'Bundesland',postal_code:'Postleitzahl',status:'Status',links:'Links',active:'Listung'};
const byId=id=>document.getElementById(id);const results=byId('changes-results'),count=byId('change-count'),days=byId('change-days'),state=byId('change-state'),type=byId('change-type');let revisions=[];
function node(tag,className,text){const item=document.createElement(tag);if(className)item.className=className;if(text!==undefined)item.textContent=text;return item}
function formatValue(field,value){if(value===null||value===undefined||value==='')return '–';if(field==='artists'&&Array.isArray(value))return value.map(item=>item.name).join(' · ');if(field==='links'&&Array.isArray(value))return value.map(item=>item.label||item.url).join(' · ');if(field==='active')return value?'gelistet':'nicht gelistet';if(field==='status')return {scheduled:'angekündigt',cancelled:'abgesagt',postponed:'verschoben'}[value]||String(value);if(typeof value==='object')return JSON.stringify(value);return String(value)}
function appendChange(target,field,values){target.append(node('dt','',FIELDS[field]||field));const detail=node('dd');if(field==='artists'){const before=values.from.map(item=>item.name),after=values.to.map(item=>item.name),removed=before.filter(name=>!after.includes(name)),added=after.filter(name=>!before.includes(name));if(removed.length)detail.append(node('del','',removed.join(' · ')),document.createTextNode(' entfällt'));if(removed.length&&added.length)detail.append(document.createTextNode(' · '));if(added.length)detail.append(node('ins','',added.join(' · ')),document.createTextNode(' neu'));if(!removed.length&&!added.length)detail.append(node('del','',formatValue(field,values.from)),document.createTextNode(' → '),node('ins','',formatValue(field,values.to)))}else detail.append(node('del','',formatValue(field,values.from)),document.createTextNode(' → '),node('ins','',formatValue(field,values.to)));target.append(detail)}
function card(revision){const event=revision.event,article=node('article',`card change-card change-${revision.display_type}`);article.id=revision.anchor;const top=node('p','change-top');top.append(node('span','badge change-kind',LABELS[revision.display_type]||revision.display_type),document.createTextNode(` Erkannt ${new Intl.DateTimeFormat('de-AT',{dateStyle:'medium',timeStyle:'short'}).format(new Date(revision.detected_at))}`));article.append(top);article.append(node('h3','',event.artists.map(item=>item.name).join(' · ')));article.append(node('p','date',new Intl.DateTimeFormat('de-AT',{weekday:'short',day:'2-digit',month:'2-digit',year:'numeric'}).format(new Date(`${event.event_date}T12:00:00`))));article.append(node('p','place',`${event.venue} · ${event.postal_code?event.postal_code+' ':''}${event.city} · ${event.state}`));const changes=node('dl','change-details');Object.entries(revision.changes||{}).filter(([field])=>field!=='source_text').forEach(([field,values])=>appendChange(changes,field,values));if(changes.children.length)article.append(changes);const anchor=node('a','change-link','Direktlink zu dieser Änderung');anchor.href=`#${revision.anchor}`;article.append(anchor);return article}
function render(){const cutoff=days.value==='all'?null:new Date(Date.now()-Number(days.value)*86400000);const visible=revisions.filter(item=>(!cutoff||new Date(item.detected_at)>=cutoff)&&(!state.value||item.event.state===state.value)&&(!type.value||item.display_type===type.value));const groups=new Map();visible.forEach(item=>{const key=item.detected_at.slice(0,10);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(item)});const sections=[];groups.forEach((items,key)=>{const section=node('section','change-day');section.append(node('h2','',new Intl.DateTimeFormat('de-AT',{dateStyle:'full'}).format(new Date(`${key}T12:00:00`))));const cards=node('div','cards');cards.append(...items.map(card));section.append(cards);sections.push(section)});results.replaceChildren(...sections);count.textContent=`${visible.length} ${visible.length===1?'Änderung':'Änderungen'} angezeigt`;const params=new URLSearchParams();if(days.value!=='90')params.set('days',days.value);if(state.value)params.set('state',state.value);if(type.value)params.set('type',type.value);history.replaceState(null,'',`${location.pathname}${params.size?'?'+params:''}${location.hash}`);if(location.hash){const target=document.getElementById(location.hash.slice(1));if(target)target.scrollIntoView()}}
async function start(){try{const response=await fetch('data/changes.json');if(!response.ok)throw new Error('HTTP');const payload=await response.json();revisions=payload.revisions;[...new Set(revisions.map(item=>item.event.state))].sort((a,b)=>a.localeCompare(b,'de')).forEach(value=>{const option=node('option','',value);option.value=value;state.append(option)});const params=new URLSearchParams(location.search);days.value=params.get('days')||'90';state.value=params.get('state')||'';type.value=params.get('type')||'';byId('changes-metadata').textContent=`Aktualisiert ${new Intl.DateTimeFormat('de-AT',{dateStyle:'medium',timeStyle:'short'}).format(new Date(payload.generated_at))}`;render()}catch{count.textContent='Die Änderungshistorie konnte nicht geladen werden.'}}
document.querySelector('.change-controls').addEventListener('input',render);start();
"""


def generate_changelog(revisions: list[dict[str, Any]], output_dir: Path, generated_at: datetime) -> None:
    atomic_write_text(output_dir / "changes.html", CHANGELOG_HTML)
    atomic_write_text(output_dir / "assets/changes.js", CHANGELOG_JS)
    atomic_write_json(
        output_dir / "data/changes.json",
        {"generated_at": generated_at.isoformat(), "revisions": changelog_revisions(revisions)},
    )
