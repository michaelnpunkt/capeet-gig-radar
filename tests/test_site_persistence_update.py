from __future__ import annotations

import json
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

import pytest

from src.config import Settings
from src.fetch import FetchResult
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
    styles = (output / "assets/styles.css").read_text()
    data = json.loads((output / "data/gigs.json").read_text())
    status_data = json.loads((output / "data/status.json").read_text())
    changes_data = json.loads((output / "data/changes.json").read_text())
    assert "Mosh Pit Crew" in html and "Big shout-out to" in html
    assert "header-metadata" in html and "Gesamt-RSS" in html and "header-feeds" not in html and "changes.html" in html
    assert "Bundesland-RSS" in html and html.count("feeds/neu-") == 9
    assert "selected-feeds" not in html and "Offene Meldungen" not in html
    assert all(state in html for state in ("Burgenland", "Kärnten", "Niederösterreich", "Oberösterreich", "Salzburg", "Steiermark", "Tirol", "Vorarlberg", "Wien"))
    assert "nur einmal täglich abgerufen" in html and "Original-Gigliste bei Capeet öffnen" in html
    assert "Abruf: 1× täglich" in html and "Capeet Original" in html
    assert 'class="nav-break"' in html and ".nav-break{flex-basis:100%" in styles
    assert "data-states=\"all\"" in html and "data-genres=\"all\"" in html and "data-genres=\"none\"" in html and "Nur Wien" not in html
    assert 'id="month"' in html and 'id="days"' in html
    assert "Hinzufügungsdatum (neueste zuerst)" in html and "Hinzufügungsdatum (älteste zuerst)" in html and "jüngste erkannte Revision" in html
    assert 'id="past" type="checkbox" checked' in html and "Vergangene Gigs ausblenden" in html
    assert 'id="cancelled" type="checkbox" checked' in html and "Abgesagte Gigs ausblenden" in html
    assert "changed-desc" in html and "date-asc" in html and "date-desc" in html
    assert 'data-view="grid"' in html and 'data-view="list"' in html and 'aria-pressed="true"' in html
    assert 'class="back-top"' in html and 'href="#top"' in html
    assert "Fehler melden" in html and "Idee vorschlagen" in html and "Sonstiges Feedback" in html and "bug_report.yml" in html
    assert "innerHTML" not in script and "textContent" in script and "safeLink" in script
    assert "data/status.json" in script and "Zuletzt geprüft" in script and "Daten geändert" in script
    assert "latest_revision" in data["events"][0] and "revisionDetails" in script and "changeRow" in script
    assert "event.latest_revision?.kind==='new'?'Neu':'Geändert'" in script and "event.revision===1?'Neu'" not in script
    assert "node('del'" in script and "node('ins'" in script and "Event abgesagt" in script
    assert "month.value" in script and "days.value" in script and "updateHeaderFeeds" not in script and "updateFeeds" not in script
    assert "listSummary" in script and "list-line" in script and "markers.push('abgesagt')" in script
    assert "past.checked" in script and "hideCancelled" in script and "data-genres" in script and "setView" in script and "params.set('view','list')" in script
    assert "'discovered-asc':(a,b)=>(a.first_seen_at||'').localeCompare(b.first_seen_at||'')" in script
    assert "@media(max-width:760px)" in styles and "--acid:#d6ff00" in styles and ".cards.list-view" in styles
    assert ".list-view .card>*{display:none}" in styles and "white-space:nowrap" in styles and "text-overflow:ellipsis" in styles
    assert {event["state"] for event in data["events"]} >= {"Wien", "Salzburg", "Steiermark", "Tirol"}
    assert changes_data["revisions"] == []
    assert status_data == {
        "checked_at": now.isoformat(),
        "changed_at": now.isoformat(),
        "source_url": "https://www.capeet.com/gigs_list.html",
        "source_changed": True,
    }
    changes_html = (output / "changes.html").read_text()
    assert "Gig<br>" in changes_html and "<span>Changelog</span>" in changes_html
    assert 'class="back-top"' in changes_html and "Fehler melden" in changes_html
    changes_script = (output / "assets/changes.js").read_text()
    assert "innerHTML" not in changes_script and "textContent" in changes_script
    assert "data/status.json" in changes_script and "Zuletzt geprüft" in changes_script and "Daten geändert" in changes_script
    assert "appendChange" in changes_script and "node('del'" in changes_script and "node('ins'" in changes_script
    assert "change-days" in changes_script and "change-state" in changes_script and "change-type" in changes_script
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


def test_304_updates_public_check_time_without_changing_data_time(tmp_path, fixture_path, monkeypatch):
    settings = Settings(data_dir=tmp_path / "data", output_dir=tmp_path / "docs", minimum_events=20)
    assert run(settings, fixture_path) == 0
    source_state_path = settings.data_dir / "source-state.json"
    original_change = "2026-08-08T05:00:00+00:00"
    source_state_path.write_text(json.dumps({
        "changed_at": original_change,
        "checked_at": original_change,
        "etag": '"abc"',
    }), encoding="utf-8")
    monkeypatch.setattr("src.update.fetch_text", lambda *args, **kwargs: FetchResult(None, 304, None))
    assert run(settings) == 0
    source_state = json.loads(source_state_path.read_text())
    public_status = json.loads((settings.output_dir / "data/status.json").read_text())
    assert source_state["checked_at"] != original_change
    assert source_state["changed_at"] == original_change
    assert public_status["checked_at"] == source_state["checked_at"]
    assert public_status["changed_at"] == original_change
    assert public_status["source_changed"] is False


def test_site_rolls_back_on_feed_failure(tmp_path, fixture_events, monkeypatch):
    output = tmp_path / "docs"
    output.mkdir()
    (output / "sentinel").write_text("old")
    monkeypatch.setattr("src.site.generate_feeds", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        generate_site(fixture_events, [], output, "https://site.example", datetime.now(timezone.utc))
    assert (output / "sentinel").read_text() == "old"
