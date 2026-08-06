from __future__ import annotations

import pytest

from src.parser import ParseError, parse_events


def test_br_parser_extracts_vienna_lineup_links_label_and_entities(fixture_path):
    events = parse_events(fixture_path.read_text(encoding="utf-8"), "https://www.capeet.com/gigs_list.html")
    assert len(events) == 20
    first = events[0]
    assert first.event_date.isoformat() == "2027-09-01"
    assert [artist.name for artist in first.artists] == ["Ätherklang", "Echo"]
    assert first.artists[0].country == "AT"
    assert first.artists[0].link == "https://artists.example/a"
    assert first.venue == "Flex"
    assert first.city == "Wien" and first.postal_code == "1010"
    assert events[1].title == "Donauinselfest"
    assert events[1].venue == "Arena Wien"
    assert events[-1].venue == "Porgy & Bess"


def test_cancellation_red_text_and_year_rollover(fixture_path):
    events = parse_events(fixture_path.read_text(encoding="utf-8"), "https://www.capeet.com/gigs_list.html")
    cancelled = next(event for event in events if event.headliner == "Delta")
    assert cancelled.status == "cancelled"
    assert events[-2].event_date.isoformat() == "2027-12-19"
    assert events[-1].event_date.isoformat() == "2028-01-02"


def test_plain_year_marker_keeps_all_following_events_in_new_year():
    html = """<html><head><title>Gigs August 2026 - Oktober 2027</title></head><body>
    30.12.: <b>December Act</b> @ <i>Club</i>, 1010 Wien<br>
    2027:<br>
    08.01.: <b>January Act</b> @ <i>Club</i>, 1010 Wien<br>
    03.02.: <b>February Act</b> @ <i>Club</i>, 1010 Wien<br>
    29.10.: <b>October Act</b> @ <i>Club</i>, 1010 Wien<br>
    </body></html>"""
    events = parse_events(html, "https://www.capeet.com/gigs_list.html")
    assert [event.event_date.isoformat() for event in events] == [
        "2026-12-30",
        "2027-01-08",
        "2027-02-03",
        "2027-10-29",
    ]


@pytest.mark.parametrize("html", ["", "<h2>Gigs 2027</h2>01.09.: ohne Struktur<br>"])
def test_empty_or_invalid_source_fails(html):
    with pytest.raises(ParseError, match="Keine gültigen"):
        parse_events(html, "https://www.capeet.com/gigs_list.html")


def test_unsafe_link_is_discarded_not_rendered():
    html = '<h2>Gigs 2027</h2>01.09.: <a href="javascript:alert(1)"><b>Band</b></a> @ <i>Club</i>, 1010 Wien<br>'
    event = parse_events(html, "https://www.capeet.com/gigs_list.html")[0]
    assert event.artists[0].link is None


def test_single_bold_lineup_splits_artists_and_lowercase_countries():
    html = '<h2>Gigs 2027</h2>01.09.: <b><a href="/a">Alpha (at)</a> / <a href="/b">Beta (d)</a> + Gamma</b> @ <i>Club</i>, 1010 Wien<br>'
    event = parse_events(html, "https://www.capeet.com/gigs_list.html")[0]
    assert [(artist.name, artist.country) for artist in event.artists] == [
        ("Alpha", "AT"),
        ("Beta", "D"),
        ("Gamma", None),
    ]
    assert event.artists[0].link == "https://www.capeet.com/a"
    assert event.artists[1].link == "https://www.capeet.com/b"


def test_combined_country_codes_are_removed_from_artist_name():
    html = '<h2>Gigs 2027</h2>01.09.: <b>MASTER (usa/cze)</b> @ <i>Club</i>, Wien<br>'
    artist = parse_events(html, "https://www.capeet.com/gigs_list.html")[0].artists[0]
    assert artist.name == "MASTER"
    assert artist.country == "USA/CZE"


def test_slash_in_city_name_is_not_moved_into_venue():
    html = '<h2>Gigs 2027</h2>01.09.: <b>Band</b> @ <i>Kulturhaus</i>, Bruck/Mur<br>'
    event = parse_events(html, "https://www.capeet.com/gigs_list.html")[0]
    assert event.venue == "Kulturhaus"
    assert event.city == "Bruck/Mur"
