from __future__ import annotations

import json

from src.genres import MusicBrainzClient, apply_genres, classify_tags
from src.locations import apply_locations


def test_austrian_locations_postcodes_aliases_and_override(tmp_path, fixture_events):
    overrides = tmp_path / "locations.json"
    overrides.write_text(json.dumps({"Spezialort": "Tirol"}), encoding="utf-8")
    apply_locations(fixture_events, overrides)
    assert fixture_events[0].state == "Wien"
    assert next(event for event in fixture_events if event.city == "St. Pölten").state == "Niederösterreich"
    assert next(event for event in fixture_events if event.city == "Linz").state == "Oberösterreich"
    fixture_events[0].city = "Wr. Neustadt"
    fixture_events[0].postal_code = None
    apply_locations(fixture_events[:1], overrides)
    assert fixture_events[0].state == "Niederösterreich"


def test_genre_override_cache_heuristic_and_taxonomy(tmp_path, fixture_events):
    overrides = tmp_path / "overrides.json"
    cache = tmp_path / "cache.json"
    overrides.write_text(json.dumps({"ätherklang": {"family": "Punk", "subgenres": ["Crust Punk"]}}), encoding="utf-8")
    cache.write_text(json.dumps({"beta band": {"family": "Metal", "subgenres": ["Doom Metal"]}}), encoding="utf-8")
    apply_genres(fixture_events[:3], overrides, cache)
    assert fixture_events[0].genre.family == "Punk" and fixture_events[0].genre.source == "override"
    assert fixture_events[1].genre.family == "Metal" and fixture_events[1].genre.source == "cache"
    assert len(fixture_events[0].genre.subgenres) <= 3
    assert classify_tags([{"name": "post-punk", "count": 8}]).family == "Goth/Post-Punk"
    assert classify_tags([{"name": "rock", "count": 1}]).family == "Unklassifiziert"


class JsonResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"artists": [{"score": 95, "tags": [{"name": "death metal", "count": 4}]}]}


class Session:
    def get(self, *args, **kwargs):
        return JsonResponse()


def test_musicbrainz_rate_limit():
    sleeps = []
    client = MusicBrainzClient("agent", interval_seconds=1.0, session=Session(), sleeper=sleeps.append)
    assert client.lookup("One").family == "Metal"
    assert client.lookup("Two").family == "Metal"
    assert sleeps and 0 < sleeps[0] <= 1.0
