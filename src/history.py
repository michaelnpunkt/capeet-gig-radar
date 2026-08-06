from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any

from .models import Event, normalize_key


TRACKED_FIELDS = ("event_date", "artists", "title", "venue", "city", "state", "postal_code", "status", "links", "source_text")


def _value(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [{field: getattr(item, field) for field in item.__dataclass_fields__} for item in value]
    return value


def _lineup(event: Event) -> str:
    return " | ".join(normalize_key(artist.name) for artist in event.artists)


def match_event(event: Event, candidates: list[Event], used: set[str]) -> Event | None:
    available = [candidate for candidate in candidates if candidate.id not in used]
    direct = next((candidate for candidate in available if candidate.id == event.id), None)
    if direct:
        return direct
    corrected_date = next((
        candidate for candidate in available
        if candidate.source_text == event.source_text
        and normalize_key(candidate.venue) == normalize_key(event.venue)
        and normalize_key(candidate.city) == normalize_key(event.city)
    ), None)
    if corrected_date:
        return corrected_date
    place = next((candidate for candidate in available if candidate.event_date == event.event_date and normalize_key(candidate.venue) == normalize_key(event.venue) and normalize_key(candidate.city) == normalize_key(event.city)), None)
    if place:
        return place
    scored: list[tuple[float, Event]] = []
    for candidate in available:
        if candidate.event_date != event.event_date:
            continue
        headliner = SequenceMatcher(None, normalize_key(candidate.headliner), normalize_key(event.headliner)).ratio()
        lineup = SequenceMatcher(None, _lineup(candidate), _lineup(event)).ratio()
        if max(headliner, lineup) >= 0.84:
            scored.append((max(headliner, lineup), candidate))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1] if scored else None


def _revision(event: Event, stamp: str, kind: str, changes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"guid": f"{event.id}:{event.revision}", "event_id": event.id, "revision": event.revision, "detected_at": stamp, "kind": kind, "changes": changes, "event": event.to_dict()}


def reconcile(current: list[Event], previous: list[Event], revisions: list[dict[str, Any]], *, now: datetime | None = None, initial_baseline: bool = False, past_event_retention_days: int = 120) -> tuple[list[Event], list[dict[str, Any]]]:
    timestamp = now or datetime.now(timezone.utc)
    stamp = timestamp.isoformat()
    used: set[str] = set()
    additions: list[dict[str, Any]] = []
    result: list[Event] = []
    for event in current:
        old = match_event(event, previous, used)
        if old is None:
            event.first_seen_at = event.last_seen_at = stamp
            event.baseline = initial_baseline
            event.revision = 0 if initial_baseline else 1
            event.changed_at = None if initial_baseline else stamp
            if not initial_baseline:
                additions.append(_revision(event, stamp, "new", {}))
            result.append(event)
            continue
        used.add(old.id)
        event.id = old.id
        event.first_seen_at = old.first_seen_at or stamp
        event.last_seen_at = stamp
        event.baseline = old.baseline
        changes = {}
        for field in TRACKED_FIELDS:
            before, after = _value(getattr(old, field)), _value(getattr(event, field))
            if before != after:
                changes[field] = {"from": before, "to": after}
        if not old.active:
            changes["active"] = {"from": False, "to": True}
        event.active = True
        event.revision = old.revision + bool(changes)
        event.changed_at = stamp if changes else old.changed_at
        if event.genre.family == "Unbekannt":
            event.genre = old.genre
        if changes:
            additions.append(_revision(event, stamp, "changed", changes))
        result.append(event)
    for old in previous:
        if old.id in used or old.event_date < timestamp.date() - timedelta(days=past_event_retention_days):
            continue
        if old.event_date >= timestamp.date() and old.active:
            old.active = False
            old.revision += 1
            old.changed_at = stamp
            additions.append(_revision(old, stamp, "unlisted", {"active": {"from": True, "to": False}}))
        result.append(old)
    result = [event for event in result if event.event_date >= timestamp.date() - timedelta(days=past_event_retention_days)]
    revision_cutoff = timestamp - timedelta(days=730)
    retained_revisions = [item for item in revisions + additions if datetime.fromisoformat(item["detected_at"]) >= revision_cutoff]
    return sorted(result, key=lambda event: (event.event_date, event.headliner.casefold())), retained_revisions
