from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from .changelog import CHANGE_LABELS, FIELD_LABELS, revision_anchor, revision_type
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
        if detected < cutoff or revision.get("kind") not in {"new", "changed", "unlisted"}:
            continue
        if state is not None and event.get("state") != state:
            continue
        selected.append(revision)
    return sorted(selected, key=lambda value: (value["detected_at"], value.get("revision", 0)), reverse=True)[:limit]


def _display_value(field: str, value: object) -> str:
    if value is None or value == "":
        return "–"
    if field == "artists" and isinstance(value, list):
        return " · ".join(str(item.get("name", "")) for item in value if isinstance(item, dict))
    if field == "links" and isinstance(value, list):
        return " · ".join(str(item.get("label") or item.get("url", "")) for item in value if isinstance(item, dict))
    if field == "active":
        return "gelistet" if value else "nicht gelistet"
    if field == "status":
        return {
            "scheduled": "angekündigt",
            "cancelled": "abgesagt",
            "postponed": "verschoben",
        }.get(str(value), str(value))
    return str(value)


def _change_summary(revision: dict) -> str:
    details = []
    for field, values in revision.get("changes", {}).items():
        if field == "source_text" or not isinstance(values, dict):
            continue
        details.append(
            f"{FIELD_LABELS.get(field, field)}: "
            f"{_display_value(field, values.get('from'))} → {_display_value(field, values.get('to'))}"
        )
    return " · ".join(details)


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
    for revision in items:
        event = revision["event"]
        item = ET.SubElement(channel, "item")
        artists = ", ".join(artist["name"] for artist in event.get("artists", []))
        display_type = revision_type(revision)
        ET.SubElement(item, "title").text = f"{CHANGE_LABELS[display_type]}: {artists} – {event['city']}"
        ET.SubElement(item, "link").text = f"{site_url}/changes.html#{revision_anchor(revision)}"
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = f"{event['id']}:{revision['revision']}"
        detected = datetime.fromisoformat(revision["detected_at"])
        if detected.tzinfo is None:
            detected = detected.replace(tzinfo=timezone.utc)
        ET.SubElement(item, "pubDate").text = format_datetime(detected)
        changed = _change_summary(revision)
        ET.SubElement(item, "description").text = f"{event['event_date']} · {event['venue']}, {event.get('postal_code') or ''} {event['city']} · {event['state']}" + (f" · {changed}" if changed else "")
    ET.indent(rss, space="  ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(rss, encoding="unicode") + "\n"


def generate_feeds(revisions: list[dict], output_dir: Path, site_url: str, now: datetime, *, limit: int = 100, days: int = 90) -> list[Path]:
    generated = []

    def write(relative: str, state: str | None, title: str) -> None:
        path = output_dir / relative
        content = _feed(_items(revisions, now, state, limit, days), title, "Neue, geänderte und nicht mehr gelistete Capeet-Konzerte in Österreich", site_url, f"{site_url}/{relative}", now)
        atomic_write_text(path, content)
        generated.append(path)

    write("feed.xml", None, "Capeet Gig Radar – Neuigkeiten")
    for state in AUSTRIAN_STATES:
        write(f"feeds/neu-{slug(state)}.xml", state, f"Capeet Gig Radar – Änderungen in {state}")
    return generated
