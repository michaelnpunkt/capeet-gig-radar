from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import requests

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
    "enns": "Oberösterreich", "lembach": "Oberösterreich", "st martin i m": "Oberösterreich",
    "salzburg": "Salzburg", "graz": "Steiermark", "leoben": "Steiermark", "bruck mur": "Steiermark",
    "innsbruck": "Tirol", "kufstein": "Tirol", "worgl": "Tirol", "bregenz": "Vorarlberg",
    "dornbirn": "Vorarlberg", "feldkirch": "Vorarlberg", "wien": "Wien", "vienna": "Wien",
}

OSM_STATE_NAMES = {
    "burgenland": "Burgenland",
    "carinthia": "Kärnten",
    "karnten": "Kärnten",
    "lower austria": "Niederösterreich",
    "niederosterreich": "Niederösterreich",
    "upper austria": "Oberösterreich",
    "oberosterreich": "Oberösterreich",
    "salzburg": "Salzburg",
    "styria": "Steiermark",
    "steiermark": "Steiermark",
    "tyrol": "Tirol",
    "tirol": "Tirol",
    "vorarlberg": "Vorarlberg",
    "vienna": "Wien",
    "wien": "Wien",
}


class LocationLookupClient:
    def __init__(
        self,
        user_agent: str,
        interval_seconds: float = 1.0,
        session: requests.Session | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.user_agent = user_agent
        self.interval_seconds = max(1.0, interval_seconds)
        self.session = session or requests.Session()
        self.sleeper = sleeper
        self.last_request_at: float | None = None

    def lookup(self, city: str) -> str | None:
        if self.last_request_at is not None:
            wait = self.interval_seconds - (time.monotonic() - self.last_request_at)
            if wait > 0:
                self.sleeper(wait)
        try:
            response = self.session.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "city": city,
                    "country": "Österreich",
                    "format": "jsonv2",
                    "addressdetails": 1,
                    "countrycodes": "at",
                    "limit": 1,
                },
                headers={"User-Agent": self.user_agent, "Accept": "application/json"},
                timeout=15,
            )
            self.last_request_at = time.monotonic()
            response.raise_for_status()
            results = response.json()
            if not results:
                return None
            address = results[0].get("address", {})
            if str(address.get("country_code", "")).casefold() != "at":
                return None
            return OSM_STATE_NAMES.get(normalize_key(str(address.get("state", ""))))
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            return None


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


def apply_locations(
    events: list[Event],
    overrides_path: Path,
    cache_path: Path | None = None,
    client: LocationLookupClient | None = None,
    *,
    max_lookups: int = 50,
) -> dict[str, str]:
    raw: dict[str, Any] = load_json(overrides_path, {})
    overrides = {normalize_key(key): value for key, value in raw.items()}
    cache: dict[str, str] = load_json(cache_path, {}) if cache_path else {}
    lookups = 0
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
        city_key = normalize_key(event.city)
        event.state = CITY_STATES.get(city_key, _postal_state(event.postal_code) or cache.get(city_key, "Unbekannt"))
        if event.state == "Unbekannt" and city_key not in cache and client is not None and lookups < max_lookups:
            resolved = client.lookup(event.city)
            lookups += 1
            if resolved in AUSTRIAN_STATES:
                cache[city_key] = resolved
                event.state = resolved
            else:
                cache[city_key] = "Unbekannt"
    return cache
