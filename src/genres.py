from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import requests

from .models import Event, Genre, normalize_key
from .persistence import load_json


GENRE_FAMILIES = (
    "Punk",
    "Hardcore",
    "Metal",
    "Alternative/Indie",
    "Goth/Post-Punk",
    "Rock",
    "Electronic/Industrial",
    "Sonstiges",
    "Unklassifiziert",
)

TAG_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Deathcore", "Metal", ("deathcore",)),
    ("Metalcore", "Metal", ("metalcore",)),
    ("Grindcore", "Metal", ("grindcore", "grind core")),
    ("Death Metal", "Metal", ("death metal", "deathmetal")),
    ("Black Metal", "Metal", ("black metal", "blackmetal")),
    ("Doom Metal", "Metal", ("doom metal", "funeral doom")),
    ("Thrash Metal", "Metal", ("thrash metal", "thrash")),
    ("Sludge Metal", "Metal", ("sludge metal", "sludge")),
    ("Stoner Metal", "Metal", ("stoner metal",)),
    ("Melodic Hardcore", "Hardcore", ("melodic hardcore",)),
    ("Hardcore Punk", "Hardcore", ("hardcore punk", "hardcore-punk", "post-hardcore")),
    ("Crust Punk", "Punk", ("crust punk", "crust")),
    ("Street Punk", "Punk", ("street punk", "oi!", "oi punk")),
    ("Ska Punk", "Punk", ("ska punk", "ska-punk")),
    ("Post-Punk", "Goth/Post-Punk", ("post-punk", "post punk", "darkwave", "coldwave", "gothic rock")),
    ("Shoegaze", "Alternative/Indie", ("shoegaze", "dream pop")),
    ("Noise Rock", "Alternative/Indie", ("noise rock",)),
    ("Industrial", "Electronic/Industrial", ("industrial metal", "industrial rock", "industrial", "ebm")),
)

FAMILY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Hardcore", ("hardcore",)),
    ("Punk", ("punk", "anarcho-punk", "pop punk", "garage punk")),
    ("Metal", ("metal", "heavy metal", "progressive metal", "power metal")),
    ("Goth/Post-Punk", ("goth", "gothic", "post-punk")),
    ("Electronic/Industrial", ("electronic", "electronica", "techno", "synthpop", "industrial")),
    ("Alternative/Indie", ("alternative", "indie", "emo", "grunge")),
    ("Rock", ("rock", "hard rock", "garage rock", "psychedelic rock", "stoner rock")),
    ("Sonstiges", ("hip hop", "hip-hop", "rap", "jazz", "folk", "country", "pop", "blues", "soul", "funk", "reggae", "ska", "classical", "experimental")),
)

CLASSIFIER_VERSION = 2


def _tag_name(value: dict[str, Any]) -> str:
    return str(value.get("name", "")).casefold().strip()


def _tag_weight(value: dict[str, Any]) -> int:
    try:
        return int(value.get("count", 0))
    except (TypeError, ValueError):
        return 0


def classify_tags(tags: list[dict[str, Any]], source: str = "lastfm") -> Genre:
    ranked = sorted(tags, key=_tag_weight, reverse=True)
    subgenres: list[str] = []
    family_scores: dict[str, int] = {}

    for subgenre, family, aliases in TAG_RULES:
        matching_weights = [
            _tag_weight(tag)
            for tag in ranked
            if _tag_weight(tag) >= 5
            and any(_tag_name(tag) == alias or alias in _tag_name(tag) for alias in aliases)
        ]
        if matching_weights:
            subgenres.append(subgenre)
            family_scores[family] = family_scores.get(family, 0) + max(matching_weights) + 20

    for family, aliases in FAMILY_RULES:
        weights = [
            _tag_weight(tag)
            for tag in ranked
            if _tag_weight(tag) >= 5
            and any(_tag_name(tag) == alias or alias in _tag_name(tag) for alias in aliases)
        ]
        if weights:
            family_scores[family] = family_scores.get(family, 0) + max(weights)

    if not family_scores:
        return Genre(source="unclassified")
    family = max(family_scores, key=family_scores.get)
    family_subgenres = [
        subgenre
        for subgenre, rule_family, _aliases in TAG_RULES
        if rule_family == family and subgenre in subgenres
    ][:3]
    return Genre(family, family_subgenres, source)


def heuristic_genre(event: Event) -> Genre:
    text = normalize_key(f"{event.title or ''} {event.source_text}")
    tags = [
        {"name": alias, "count": 5}
        for _subgenre, _family, aliases in TAG_RULES
        for alias in aliases
        if normalize_key(alias) in text
    ]
    return classify_tags(tags, "heuristic") if tags else Genre(source="unclassified")


def _coerce(value: Any, default_source: str) -> Genre:
    if isinstance(value, str):
        return Genre(value if value in GENRE_FAMILIES else "Unklassifiziert", [], default_source)
    if isinstance(value, dict):
        family = str(value.get("family", "Unklassifiziert"))
        source = str(value.get("source", default_source))
        return Genre(
            family if family in GENRE_FAMILIES else "Unklassifiziert",
            list(value.get("subgenres", [])),
            source,
        )
    return Genre(source="unclassified")


class LastFmClient:
    def __init__(
        self,
        api_key: str,
        user_agent: str,
        interval_seconds: float = 0.25,
        session: requests.Session | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key
        self.user_agent = user_agent
        self.interval_seconds = max(0.2, interval_seconds)
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
                "https://ws.audioscrobbler.com/2.0/",
                params={
                    "method": "artist.getTopTags",
                    "artist": artist,
                    "api_key": self.api_key,
                    "format": "json",
                    "autocorrect": "0",
                },
                headers={"User-Agent": self.user_agent, "Accept": "application/json"},
                timeout=15,
            )
            self.last_request_at = time.monotonic()
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                return Genre(source="unclassified" if int(payload.get("error", 0)) == 6 else "lookup_failed")
            tags = payload.get("toptags", {}).get("tag", [])
            return classify_tags(tags, "lastfm")
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            return Genre(source="lookup_failed")


def _cache_value(genre: Genre) -> dict[str, Any]:
    return {
        "family": genre.family,
        "subgenres": genre.subgenres,
        "source": genre.source,
        "classifier_version": CLASSIFIER_VERSION,
    }


def _usable_cache_value(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("source") not in {"lastfm", "unclassified"}:
        return False
    return value.get("family") != "Unklassifiziert" or value.get("classifier_version") == CLASSIFIER_VERSION


def uncached_artist_count(events: list[Event], overrides_path: Path, cache_path: Path) -> int:
    overrides = {normalize_key(key) for key in load_json(overrides_path, {})}
    cache_data = load_json(cache_path, {})
    cache = {
        normalize_key(key)
        for key, value in cache_data.items()
        if _usable_cache_value(value)
    }
    artists = {normalize_key(artist.name) for event in events for artist in event.artists}
    return len({key for key in artists if key and key not in overrides and key not in cache})


def apply_genres(
    events: list[Event],
    overrides_path: Path,
    cache_path: Path,
    client: LastFmClient | None = None,
    *,
    max_lookups: int = 1200,
) -> dict[str, Any]:
    overrides = {normalize_key(key): value for key, value in load_json(overrides_path, {}).items()}
    cache: dict[str, Any] = load_json(cache_path, {})
    lookups = 0

    artist_genres: dict[str, Genre] = {}
    for event in events:
        for artist in event.artists:
            key = normalize_key(artist.name)
            if not key or key in artist_genres:
                continue
            if key in overrides:
                genre = _coerce(overrides[key], "override")
            elif key in cache and _usable_cache_value(cache[key]):
                genre = _coerce(cache[key], "cache")
            elif client is not None and lookups < max_lookups:
                genre = client.lookup(artist.name)
                if genre.source != "lookup_failed":
                    cache[key] = _cache_value(genre)
                else:
                    genre = Genre(source="unclassified")
                lookups += 1
            else:
                genre = Genre(source="unclassified")
            artist_genres[key] = genre

    for event in events:
        headliner_key = normalize_key(event.headliner)
        event.genre = artist_genres.get(headliner_key, heuristic_genre(event))
        if event.genre.family == "Unklassifiziert":
            heuristic = heuristic_genre(event)
            if heuristic.family != "Unklassifiziert":
                event.genre = heuristic
    return cache
