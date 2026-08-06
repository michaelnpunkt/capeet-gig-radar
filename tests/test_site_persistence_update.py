from __future__ import annotations

import json
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

import pytest

from src.config import Settings
from src.history import reconcile
from src.locations import apply_locations
from src.persistence import atomic_write_json
from src.site import generate_site
from src.update import run


def test_atomic_json(tmp_path):
    path = tmp_path / "nested/state.json"
    atomic_write_json(path, {"old": True})
    atomic_write_json(path, {"new": "ä"})
    assert json.loads(path.read_text()) == {"new": "ä"}
    assert list(path.parent.glob(f".{path.name}.*")) == []


def test_site_multifilter_safe_dom_sorts_and_valid_feeds(tmp_path, fixture_events):
    apply_locations(fixture_events, tmp_path / "none.json")
    now = datetime(2027, 8, 1, tzinfo=timezone.utc)
    baseline, _ = reconcile(fixture_events, [], [], now=now, initial_baseline=True)
    output = tmp_path / "docs"
    generate_site(baseline, [], output, "https://site.example", now)
    html = (output / "index.html").read_text()
    script = (output / "assets/app.js").read_text()
    data = json.loads((output / "data/gigs.json").read_text())
    assert "Capeet Gig Radar Österreich" in html and "Inoffizieller Filter" in html
    assert "data-states=\"all\"" in html and "Nur Wien" in html
    assert "changed-desc" in html and "date-asc" in html and "date-desc" in html
    assert "innerHTML" not in script and "textContent" in script and "safeLink" in script
    assert {event["state"] for event in data["events"]} >= {"Wien", "Salzburg", "Steiermark", "Tirol"}
    for feed in output.glob("**/*.xml"):
        ET.parse(feed)
    assert "<item>" not in (output / "feed.xml").read_text()


def test_script_content_remains_data_not_html(tmp_path, fixture_events):
    fixture_events[0].source_text = '<script>alert("x")</script>'
    output = tmp_path / "docs"
    generate_site(fixture_events, [], output, "https://site.example", datetime.now(timezone.utc))
    assert "<script>alert" not in (output / "index.html").read_text()
    assert '<script>alert("x")</script>' in json.loads((output / "data/gigs.json").read_text())["events"][0]["source_text"]


def test_offline_update_and_idempotent_second_run(tmp_path, fixture_path):
    settings = Settings(data_dir=tmp_path / "data", output_dir=tmp_path / "docs", minimum_events=20)
    assert run(settings, fixture_path) == 0
    first = json.loads((settings.data_dir / "events.json").read_text())
    assert len(first) == 20 and (settings.output_dir / "index.html").exists()
    assert run(settings, fixture_path) == 0
    second = json.loads((settings.data_dir / "events.json").read_text())
    assert [event["revision"] for event in second] == [event["revision"] for event in first]


def test_site_rolls_back_on_feed_failure(tmp_path, fixture_events, monkeypatch):
    output = tmp_path / "docs"
    output.mkdir()
    (output / "sentinel").write_text("old")
    monkeypatch.setattr("src.site.generate_feeds", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        generate_site(fixture_events, [], output, "https://site.example", datetime.now(timezone.utc))
    assert (output / "sentinel").read_text() == "old"
