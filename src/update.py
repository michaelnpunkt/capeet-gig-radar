from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .fetch import FetchResult, fetch_text
from .genres import MusicBrainzClient, apply_genres
from .guardrails import validate_update
from .history import reconcile
from .locations import apply_locations
from .models import Event
from .parser import parse_events
from .persistence import atomic_write_json, load_json
from .site import generate_site


def _events(path: Path) -> list[Event]:
    return [Event.from_dict(value) for value in load_json(path, [])]


def run(settings: Settings, input_path: Path | None = None, use_musicbrainz: bool = False, dry_run: bool = False) -> int:
    events_path = settings.data_dir / "events.json"
    revisions_path = settings.data_dir / "revisions.json"
    source_state_path = settings.data_dir / "source-state.json"
    previous = _events(events_path)
    fetch_result: FetchResult | None = None
    if input_path is None:
        fetch_result = fetch_text(settings.source_url, source_state_path, timeout=settings.timeout_seconds, user_agent=settings.user_agent)
        if fetch_result.status_code == 304:
            if not settings.output_dir.joinpath("index.html").exists():
                raise RuntimeError("HTTP 304 ohne vorhandene Pages-Ausgabe")
            print("Unverändert: HTTP 304; vorhandene docs werden veröffentlicht")
            return 0
        html = fetch_result.content or ""
    else:
        html = input_path.read_text(encoding="utf-8")
    current = parse_events(html, settings.source_url)
    apply_locations(current, settings.data_dir / "location-overrides.json")
    client = MusicBrainzClient(settings.user_agent, settings.musicbrainz_interval_seconds) if use_musicbrainz else None
    genre_cache = apply_genres(current, settings.data_dir / "genre-overrides.json", settings.data_dir / "genre-cache.json", client, max_lookups=settings.musicbrainz_limit)
    validate_update(current, previous, settings.minimum_events, settings.maximum_drop_ratio)
    now = datetime.now(timezone.utc)
    events, revisions = reconcile(current, previous, load_json(revisions_path, []), now=now, initial_baseline=not previous, past_event_retention_days=settings.past_event_retention_days)
    if dry_run:
        print(f"Validierung erfolgreich: {len(events)} Veranstaltungen, {len(revisions)} Revisionen")
        return 0
    source_state = load_json(source_state_path, {})
    source_state.update(fetch_result.validators if fetch_result and fetch_result.validators else {})
    source_state["checked_at"] = now.isoformat()
    source_state["changed_at"] = now.isoformat()
    generate_site(events, revisions, settings.output_dir, settings.site_url, now, feed_limit=settings.feed_limit, feed_days=settings.feed_days)
    atomic_write_json(events_path, [event.to_dict() for event in events])
    atomic_write_json(revisions_path, revisions)
    atomic_write_json(settings.data_dir / "genre-cache.json", genre_cache)
    if fetch_result:
        atomic_write_json(source_state_path, source_state)
    print(f"Aktualisiert: {len(events)} Veranstaltungen, {len(revisions)} Revisionen")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capeet-Konzerte aktualisieren und GitHub-Pages-Dateien erzeugen")
    parser.add_argument("--input", type=Path, help="Lokale HTML-Datei statt Netzwerkabruf")
    parser.add_argument("--musicbrainz", action="store_true", help="Bis zu 25 unbekannte Genres bei MusicBrainz suchen")
    parser.add_argument("--dry-run", action="store_true", help="Nur parsen und prüfen")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        return run(Settings.from_env(), arguments.input, arguments.musicbrainz, arguments.dry_run)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
