from __future__ import annotations

import json

from src.genres import LastFmClient, apply_genres, classify_tags, uncached_artist_count
from src.models import Genre
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
    cache.write_text(json.dumps({"beta band": {"family": "Metal", "subgenres": ["Doom Metal"], "source": "lastfm"}}), encoding="utf-8")
    apply_genres(fixture_events[:3], overrides, cache)
    assert fixture_events[0].genre.family == "Punk" and fixture_events[0].genre.source == "override"
    assert fixture_events[1].genre.family == "Metal" and fixture_events[1].genre.source == "lastfm"
    assert len(fixture_events[0].genre.subgenres) <= 3
    assert classify_tags([{"name": "post-punk", "count": 8}]).family == "Goth/Post-Punk"
    assert classify_tags([{"name": "rock", "count": 1}]).family == "Unklassifiziert"
    specific = classify_tags([{"name": "metal", "count": 100}, {"name": "deathcore", "count": 90}])
    assert specific.family == "Metal" and specific.subgenres == ["Deathcore"]


class JsonResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"toptags": {"tag": [{"name": "death metal", "count": 40}, {"name": "metal", "count": 100}]}}


class Session:
    def get(self, *args, **kwargs):
        return JsonResponse()


def test_lastfm_rate_limit_and_request_shape():
    sleeps = []
    session = Session()
    client = LastFmClient("key", "agent", interval_seconds=0.2, session=session, sleeper=sleeps.append)
    assert client.lookup("One").family == "Metal"
    assert client.lookup("Two").family == "Metal"
    assert sleeps and 0 < sleeps[0] <= 0.2


class FakeLastFmClient:
    def __init__(self):
        self.calls = []

    def lookup(self, artist):
        self.calls.append(artist)
        return Genre("Metal" if artist == "Ätherklang" else "Punk", ["Death Metal"] if artist == "Ätherklang" else ["Street Punk"], "lastfm")


def test_every_artist_is_cached_but_headliner_sets_event_genre(tmp_path, fixture_events):
    overrides = tmp_path / "overrides.json"
    cache = tmp_path / "cache.json"
    overrides.write_text("{}", encoding="utf-8")
    cache.write_text("{}", encoding="utf-8")
    client = FakeLastFmClient()
    result = apply_genres(fixture_events[:1], overrides, cache, client)
    assert client.calls == ["Ätherklang", "Echo"]
    assert set(result) == {"atherklang", "echo"}
    assert fixture_events[0].genre.family == "Metal"
    assert uncached_artist_count(fixture_events[:1], overrides, cache) == 2

    cache.write_text(json.dumps(result), encoding="utf-8")
    second_client = FakeLastFmClient()
    apply_genres(fixture_events[:1], overrides, cache, second_client)
    assert second_client.calls == []
