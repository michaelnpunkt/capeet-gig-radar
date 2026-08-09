from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .fetch import FetchResult, fetch_text
from .genres import LastFmClient, apply_genres, uncached_artist_count
from .guardrails import validate_update
from .history import reconcile
from .locations import CITY_STATES, LocationLookupClient, apply_locations
from .models import Event, normalize_key
from .parser import parse_events
from .persistence import atomic_write_json, load_json
from .site import generate_site


def _events(path: Path) -> list[Event]:
    return [Event.from_dict(value) for value in load_json(path, [])]


def _write_check_status(settings: Settings, source_state_path: Path, now: datetime, *, changed: bool) -> dict:
    source_state = load_json(source_state_path, {})
    source_state["checked_at"] = now.isoformat()
    if changed or not source_state.get("changed_at"):
        source_state["changed_at"] = now.isoformat()
    atomic_write_json(source_state_path, source_state)
    atomic_write_json(settings.output_dir / "data/status.json", {
        "checked_at": source_state["checked_at"],
        "changed_at": source_state["changed_at"],
        "source_url": settings.source_url,
        "source_changed": changed,
    })
    return source_state


def run(settings: Settings, input_path: Path | None = None, use_lastfm: bool = False, dry_run: bool = False) -> int:
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
            location_cache = load_json(settings.data_dir / "location-cache.json", {})
            pending_locations = any(
                event.state == "Unbekannt"
                and (
                    normalize_key(event.city) in CITY_STATES
                    or normalize_key(event.city) not in location_cache
                )
                for event in previous
            )
            pending_genres = uncached_artist_count(
                previous,
                settings.data_dir / "genre-overrides.json",
                settings.data_dir / "genre-cache.json",
            )
            genre_lookup_available = use_lastfm and settings.lastfm_api_key and pending_genres > 0
            if not pending_locations and not genre_lookup_available:
                if not dry_run:
                    _write_check_status(settings, source_state_path, datetime.now(timezone.utc), changed=False)
                print("Geprüft: HTTP 304; Quelle unverändert")
                return 0
            current = previous
        else:
            current = parse_events(fetch_result.content or "", settings.source_url)
    else:
        current = parse_events(input_path.read_text(encoding="utf-8"), settings.source_url)
    location_cache_path = settings.data_dir / "location-cache.json"
    location_cache = apply_locations(
        current,
        settings.data_dir / "location-overrides.json",
        location_cache_path,
        LocationLookupClient(settings.user_agent) if input_path is None else None,
        max_lookups=settings.location_lookup_limit,
    )
    client = None
    if use_lastfm and settings.lastfm_api_key:
        client = LastFmClient(settings.lastfm_api_key, settings.user_agent, settings.lastfm_interval_seconds)
    genre_cache = apply_genres(
        current,
        settings.data_dir / "genre-overrides.json",
        settings.data_dir / "genre-cache.json",
        client,
        max_lookups=settings.lastfm_limit,
    )
    validate_update(current, previous, settings.minimum_events, settings.maximum_drop_ratio)
    now = datetime.now(timezone.utc)
    events, revisions = reconcile(current, previous, load_json(revisions_path, []), now=now, initial_baseline=not previous, past_event_retention_days=settings.past_event_retention_days)
    if dry_run:
        print(f"Validierung erfolgreich: {len(events)} Veranstaltungen, {len(revisions)} Revisionen")
        return 0
    source_state = load_json(source_state_path, {})
    source_state.update(fetch_result.validators if fetch_result and fetch_result.validators else {})
    source_state["checked_at"] = now.isoformat()
    source_changed = fetch_result is None or fetch_result.status_code == 200
    if source_changed or not source_state.get("changed_at"):
        source_state["changed_at"] = now.isoformat()
    generate_site(
        events,
        revisions,
        settings.output_dir,
        settings.site_url,
        now,
        source_checked_at=now,
        source_changed_at=datetime.fromisoformat(source_state["changed_at"]),
        source_changed=source_changed,
        feed_limit=settings.feed_limit,
        feed_days=settings.feed_days,
    )
    atomic_write_json(events_path, [event.to_dict() for event in events])
    atomic_write_json(revisions_path, revisions)
    atomic_write_json(settings.data_dir / "genre-cache.json", genre_cache)
    atomic_write_json(location_cache_path, location_cache)
    if fetch_result:
        atomic_write_json(source_state_path, source_state)
    print(f"Aktualisiert: {len(events)} Veranstaltungen, {len(revisions)} Revisionen")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capeet-Konzerte aktualisieren und GitHub-Pages-Dateien erzeugen")
    parser.add_argument("--input", type=Path, help="Lokale HTML-Datei statt Netzwerkabruf")
    parser.add_argument("--lastfm", action="store_true", help="Unbekannte Künstler über Last.fm klassifizieren")
    parser.add_argument("--dry-run", action="store_true", help="Nur parsen und prüfen")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        return run(Settings.from_env(), arguments.input, arguments.lastfm, arguments.dry_run)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
