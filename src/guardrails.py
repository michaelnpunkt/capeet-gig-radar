from __future__ import annotations

from collections import Counter

from .models import Event


class GuardrailError(RuntimeError):
    pass


def validate_update(current: list[Event], previous: list[Event], minimum: int = 20, maximum_drop_ratio: float = 0.40) -> None:
    if not current:
        raise GuardrailError("Keine Events gefunden")
    if len(current) < minimum:
        raise GuardrailError(f"Nur {len(current)} Events gefunden; mindestens {minimum} erwartet")
    active_previous = [event for event in previous if event.active]
    if active_previous and 1 - len(current) / len(active_previous) > maximum_drop_ratio:
        drop = 1 - len(current) / len(active_previous)
        raise GuardrailError(f"Eventzahl fiel um {drop:.0%}; erlaubt sind höchstens {maximum_drop_ratio:.0%}")
    duplicates = [key for key, count in Counter(event.id for event in current).items() if count > 1]
    if duplicates:
        raise GuardrailError(f"Doppelte Event-IDs: {', '.join(duplicates)}")
