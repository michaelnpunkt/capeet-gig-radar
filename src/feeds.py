from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from .locations import AUSTRIAN_STATES
from .persistence import atomic_write_text


def slug(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", "-", folded).strip("-")


def _items(revisions: list[dict], now: datetime, state: str | None, limit: int, days: int) -> list[dict]:
    cutoff = now - timedelta(days=days)
    selected = []
    for revision in revisions:
        event = revision.get("event", {})
        detected = datetime.fromisoformat(revision["detected_at"])
        if detected.tzinfo is None:
            detected = detected.replace(tzinfo=timezone.utc)
        if detected < cutoff or event.get("baseline") or revision.get("kind") not in {"new", "changed", "unlisted"}:
            continue
        if state is not None and event.get("state") != state:
            continue
        selected.append(revision)
    return sorted(selected, key=lambda value: (value["detected_at"], value.get("revision", 0)), reverse=True)[:limit]


def _feed(items: list[dict], title: str, description: str, site_url: str, feed_url: str, now: datetime) -> str:
    ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "link").text = site_url
    ET.SubElement(channel, "description").text = description
    ET.SubElement(channel, "language").text = "de-AT"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(now)
    ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link", {"href": feed_url, "rel": "self", "type": "application/rss+xml"})
    labels = {"new": "Neu", "changed": "Geändert", "unlisted": "Nicht mehr gelistet"}
    for revision in items:
        event = revision["event"]
        item = ET.SubElement(channel, "item")
        artists = ", ".join(artist["name"] for artist in event.get("artists", []))
        ET.SubElement(item, "title").text = f"{labels[revision['kind']]}: {artists} – {event['city']}"
        links = [link["url"] for link in event.get("links", []) if urlparse(link.get("url", "")).scheme in {"http", "https"}]
        ET.SubElement(item, "link").text = links[0] if links else site_url
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = f"{event['id']}:{revision['revision']}"
        detected = datetime.fromisoformat(revision["detected_at"])
        if detected.tzinfo is None:
            detected = detected.replace(tzinfo=timezone.utc)
        ET.SubElement(item, "pubDate").text = format_datetime(detected)
        changed = ", ".join(revision.get("changes", {}))
        ET.SubElement(item, "description").text = f"{event['event_date']} · {event['venue']}, {event.get('postal_code') or ''} {event['city']} · {event['state']}" + (f" · Geändert: {changed}" if changed else "")
    ET.indent(rss, space="  ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(rss, encoding="unicode") + "\n"


def generate_feeds(revisions: list[dict], output_dir: Path, site_url: str, now: datetime, *, limit: int = 100, days: int = 90) -> list[Path]:
    generated = []

    def write(relative: str, state: str | None, title: str) -> None:
        path = output_dir / relative
        content = _feed(_items(revisions, now, state, limit, days), title, "Neue und geänderte Capeet-Konzerte in Österreich", site_url, f"{site_url}/{relative}", now)
        atomic_write_text(path, content)
        generated.append(path)

    write("feed.xml", None, "Capeet Gig Radar – Neuigkeiten")
    for state in AUSTRIAN_STATES:
        write(f"feeds/neu-{slug(state)}.xml", state, f"Capeet Gig Radar – Neu in {state}")
    return generated
