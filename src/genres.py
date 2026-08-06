from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import requests

from .models import Event, Genre, normalize_key
from .persistence import load_json


GENRE_FAMILIES = (
    "Punk", "Hardcore", "Metal", "Alternative/Indie", "Goth/Post-Punk",
    "Rock", "Electronic/Industrial", "Sonstiges", "Unklassifiziert",
)
RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Goth/Post-Punk", ("post-punk", "gothic rock", "darkwave", "coldwave")),
    ("Hardcore", ("hardcore punk", "melodic hardcore", "hardcore")),
    ("Punk", ("crust punk", "street punk", "ska punk", "punk")),
    ("Metal", ("death metal", "black metal", "doom metal", "thrash metal", "sludge metal", "stoner metal", "metalcore", "deathcore", "grindcore", "metal")),
    ("Electronic/Industrial", ("industrial", "electronic", "ebm", "techno", "noise")),
    ("Alternative/Indie", ("noise rock", "shoegaze", "alternative", "indie")),
    ("Rock", ("rock", "grunge", "stoner rock")),
)


def classify_tags(tags: list[dict[str, Any]]) -> Genre:
    ranked = sorted(tags, key=lambda value: int(value.get("count", 0)), reverse=True)
    strong = [str(value.get("name", "")).casefold() for value in ranked if int(value.get("count", 0)) >= 2][:12]
    for family, needles in RULES:
        matches = [tag for tag in strong if any(needle == tag or needle in tag for needle in needles)]
        if matches:
            return Genre(family, matches[:3], "musicbrainz")
    return Genre(source="unclassified")


def heuristic_genre(event: Event) -> Genre:
    text = f"{event.title or ''} {event.source_text}".casefold()
    for family, needles in RULES:
        matches = [needle for needle in needles if re_word(needle, text)]
        if matches:
            return Genre(family, matches[:3], "heuristic")
    return Genre(source="unclassified")


def re_word(needle: str, text: str) -> bool:
    padded = f" {text.replace('-', ' ')} "
    return f" {needle.replace('-', ' ')} " in padded


def _coerce(value: Any, source: str) -> Genre:
    if isinstance(value, str):
        return Genre(value if value in GENRE_FAMILIES else "Unklassifiziert", [], source)
    if isinstance(value, dict):
        family = str(value.get("family", "Unklassifiziert"))
        return Genre(family if family in GENRE_FAMILIES else "Unklassifiziert", list(value.get("subgenres", [])), source)
    return Genre()


class MusicBrainzClient:
    def __init__(self, user_agent: str, interval_seconds: float = 1.0, session: requests.Session | None = None, sleeper: Callable[[float], None] = time.sleep) -> None:
        self.user_agent = user_agent
        self.interval_seconds = max(1.0, interval_seconds)
        self.session = session or requests.Session()
        self.sleeper = sleeper
        self.last_request_at: float | None = None

    def lookup(self, artist: str) -> Genre:
        if self.last_request_at is not None:
            wait = self.interval_seconds - (time.monotonic() - self.last_request_at)
            if wait > 0:
                self.sleeper(wait)
        try:
            response = self.session.get(
                "https://musicbrainz.org/ws/2/artist/",
                params={"query": f'artist:"{artist}"', "fmt": "json", "limit": 1},
                headers={"User-Agent": self.user_agent, "Accept": "application/json"},
                timeout=15,
            )
            self.last_request_at = time.monotonic()
            response.raise_for_status()
            artists = response.json().get("artists", [])
            if not artists or int(artists[0].get("score", 0)) < 95:
                return Genre(source="musicbrainz")
            return classify_tags(artists[0].get("tags", []))
        except (requests.RequestException, ValueError, TypeError):
            return Genre(source="musicbrainz")


def apply_genres(events: list[Event], overrides_path: Path, cache_path: Path, client: MusicBrainzClient | None = None, *, max_lookups: int = 25) -> dict[str, Any]:
    overrides = {normalize_key(key): value for key, value in load_json(overrides_path, {}).items()}
    cache: dict[str, Any] = load_json(cache_path, {})
    lookups = 0
    for event in events:
        key = normalize_key(event.headliner)
        if key in overrides:
            event.genre = _coerce(overrides[key], "override")
        elif key in cache:
            event.genre = _coerce(cache[key], "cache")
        elif client is not None and lookups < max_lookups:
            event.genre = client.lookup(event.headliner)
            cache[key] = {"family": event.genre.family, "subgenres": event.genre.subgenres}
            lookups += 1
        else:
            event.genre = heuristic_genre(event)
    return cache
