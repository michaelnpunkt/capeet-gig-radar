from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone

from .models import Event


class GuardrailError(RuntimeError):
    pass


def validate_update(current: list[Event], previous: list[Event], minimum: int = 20, maximum_drop_ratio: float = 0.40, *, today: date | None = None) -> None:
    if not current:
        raise GuardrailError("Keine Events gefunden")
    if len(current) < minimum:
        raise GuardrailError(f"Nur {len(current)} Events gefunden; mindestens {minimum} erwartet")
    today = today or datetime.now(timezone.utc).date()
    upcoming_previous = [event for event in previous if event.active and event.event_date >= today]
    upcoming_current = [event for event in current if event.event_date >= today]
    if upcoming_previous and 1 - len(upcoming_current) / len(upcoming_previous) > maximum_drop_ratio:
        drop = 1 - len(upcoming_current) / len(upcoming_previous)
        raise GuardrailError(f"Eventzahl fiel um {drop:.0%}; erlaubt sind höchstens {maximum_drop_ratio:.0%}")
    duplicates = [key for key, count in Counter(event.id for event in current).items() if count > 1]
    if duplicates:
        raise GuardrailError(f"Doppelte Event-IDs: {', '.join(duplicates)}")
