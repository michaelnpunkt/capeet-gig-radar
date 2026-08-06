from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import Event, normalize_key
from .persistence import load_json


AUSTRIAN_STATES = (
    "Burgenland", "Kärnten", "Niederösterreich", "Oberösterreich", "Salzburg",
    "Steiermark", "Tirol", "Vorarlberg", "Wien",
)
STATES = AUSTRIAN_STATES + ("Unbekannt",)

CITY_STATES = {
    "eisenstadt": "Burgenland", "rust": "Burgenland",
    "klagenfurt": "Kärnten", "villach": "Kärnten", "dobriach": "Kärnten",
    "st polten": "Niederösterreich", "krems": "Niederösterreich", "wr neustadt": "Niederösterreich", "wiener neustadt": "Niederösterreich",
    "linz": "Oberösterreich", "wels": "Oberösterreich", "steyr": "Oberösterreich",
    "salzburg": "Salzburg", "graz": "Steiermark", "leoben": "Steiermark",
    "innsbruck": "Tirol", "kufstein": "Tirol", "worgl": "Tirol", "bregenz": "Vorarlberg",
    "dornbirn": "Vorarlberg", "feldkirch": "Vorarlberg", "wien": "Wien", "vienna": "Wien",
}


def _postal_state(postal_code: str | None) -> str | None:
    if not postal_code or not postal_code.isdigit() or len(postal_code) != 4:
        return None
    first = postal_code[0]
    if first == "1":
        return "Wien"
    if first in {"2", "3"}:
        return "Niederösterreich"
    if first == "4":
        return "Oberösterreich"
    if first == "5":
        return "Salzburg"
    if first == "6":
        return "Tirol" if int(postal_code) < 6700 else "Vorarlberg"
    return {"7": "Burgenland", "8": "Steiermark", "9": "Kärnten"}.get(first)


def apply_locations(events: list[Event], overrides_path: Path) -> list[Event]:
    raw: dict[str, Any] = load_json(overrides_path, {})
    overrides = {normalize_key(key): value for key, value in raw.items()}
    for event in events:
        override = (
            overrides.get(normalize_key(f"{event.venue}, {event.city}"))
            or overrides.get(normalize_key(event.city))
            or overrides.get(normalize_key(event.postal_code or ""))
        )
        if isinstance(override, str):
            event.state = override if override in STATES else "Unbekannt"
            continue
        if isinstance(override, dict):
            event.venue = str(override.get("venue", event.venue))
            event.city = str(override.get("city", event.city))
            event.postal_code = str(override.get("postal_code", event.postal_code or "")) or None
            candidate = str(override.get("state", "Unbekannt"))
            event.state = candidate if candidate in STATES else "Unbekannt"
            continue
        event.state = CITY_STATES.get(normalize_key(event.city), _postal_state(event.postal_code) or "Unbekannt")
    return events
