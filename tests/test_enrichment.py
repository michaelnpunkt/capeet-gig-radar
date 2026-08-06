from __future__ import annotations

import json

from src.genres import LastFmClient, apply_genres, classify_tags, uncached_artist_count
from src.models import Genre
from src.locations import LocationLookupClient, apply_locations


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
    fixture_events[0].city = "St. Martin i.M."
    apply_locations(fixture_events[:1], overrides)
    assert fixture_events[0].state == "Oberösterreich"


class FakeLocationClient:
    def __init__(self):
        self.calls = []

    def lookup(self, city):
        self.calls.append(city)
        return "Oberösterreich" if city == "Vöcklabruck" else None


def test_unknown_location_uses_and_persists_lookup_cache(tmp_path, fixture_events):
    overrides = tmp_path / "locations.json"
    cache = tmp_path / "location-cache.json"
    overrides.write_text("{}", encoding="utf-8")
    cache.write_text("{}", encoding="utf-8")
    fixture_events[0].city = "Vöcklabruck"
    fixture_events[0].postal_code = None
    client = FakeLocationClient()
    result = apply_locations(fixture_events[:1], overrides, cache, client)
    assert fixture_events[0].state == "Oberösterreich"
    assert client.calls == ["Vöcklabruck"]
    assert result == {"vocklabruck": "Oberösterreich"}

    cache.write_text(json.dumps(result), encoding="utf-8")
    second_client = FakeLocationClient()
    apply_locations(fixture_events[:1], overrides, cache, second_client)
    assert second_client.calls == []


class LocationJsonResponse:
    def __init__(self, country_code="at", state="Upper Austria"):
        self.country_code = country_code
        self.state = state

    def raise_for_status(self):
        return None

    def json(self):
        return [{"address": {"country_code": self.country_code, "state": self.state}}]


class LocationSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_nominatim_lookup_is_restricted_to_austria():
    session = LocationSession(LocationJsonResponse())
    client = LocationLookupClient("agent", session=session)
    assert client.lookup("Vöcklabruck") == "Oberösterreich"
    _url, request = session.calls[0]
    assert request["params"]["countrycodes"] == "at"
    assert request["params"]["city"] == "Vöcklabruck"
    assert request["params"]["country"] == "Österreich"

    foreign = LocationLookupClient(
        "agent",
        session=LocationSession(LocationJsonResponse(country_code="de", state="Bavaria")),
    )
    assert foreign.lookup("Neustadt") is None


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
    assert classify_tags([{"name": "jazz", "count": 20}]).family == "Sonstiges"
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


def test_legacy_unclassified_cache_entry_is_rechecked_once(tmp_path, fixture_events):
    overrides = tmp_path / "overrides.json"
    cache = tmp_path / "cache.json"
    overrides.write_text("{}", encoding="utf-8")
    cache.write_text(json.dumps({"atherklang": {
        "family": "Unklassifiziert",
        "subgenres": [],
        "source": "unclassified",
    }}), encoding="utf-8")
    client = FakeLastFmClient()
    result = apply_genres(fixture_events[:1], overrides, cache, client)
    assert "Ätherklang" in client.calls
    assert result["atherklang"]["classifier_version"] == 2
