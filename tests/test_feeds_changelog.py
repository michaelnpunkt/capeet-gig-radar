from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from src.changelog import changelog_revisions, revision_anchor, revision_type
from src.feeds import generate_feeds
from src.history import reconcile
from src.site import generate_site


NOW = datetime(2027, 8, 2, tzinfo=timezone.utc)


def _changed_baseline(fixture_events):
    baseline, _ = reconcile(fixture_events, [], [], now=NOW, initial_baseline=True)
    current = deepcopy(fixture_events)
    current[0].venue = "Neues Flex"
    _events, revisions = reconcile(current, baseline, [], now=NOW)
    return revisions


def test_later_baseline_change_is_in_feed_with_changelog_permalink(tmp_path, fixture_events):
    revisions = _changed_baseline(fixture_events)
    assert revisions[0]["event"]["baseline"] is True
    generate_feeds(revisions, tmp_path, "https://site.example", NOW)
    root = ET.parse(tmp_path / "feed.xml").getroot()
    item = root.find("./channel/item")
    assert item is not None
    assert item.findtext("title").startswith("Geändert: Ätherklang, Echo")
    assert item.findtext("link") == f"https://site.example/changes.html#{revision_anchor(revisions[0])}"
    assert "Venue: Flex → Neues Flex" in item.findtext("description")
    assert item.findtext("guid") == f"{revisions[0]['event_id']}:1"


def test_revision_display_types_cover_status_and_reactivation(fixture_events):
    event = fixture_events[0].to_dict()
    cancelled = {"kind": "changed", "changes": {"status": {"from": "scheduled", "to": "cancelled"}}, "event": event}
    postponed = {"kind": "changed", "changes": {"status": {"from": "scheduled", "to": "postponed"}}, "event": event}
    reactivated = {"kind": "changed", "changes": {"active": {"from": False, "to": True}}, "event": event}
    assert revision_type(cancelled) == "cancelled"
    assert revision_type(postponed) == "postponed"
    assert revision_type(reactivated) == "reactivated"


def test_changelog_contains_full_revision_data_but_not_embedded_html(tmp_path, fixture_events):
    revisions = _changed_baseline(fixture_events)
    revisions[0]["event"]["source_text"] = '<script>alert("revision")</script>'
    generate_site(fixture_events, revisions, tmp_path, "https://site.example", NOW)
    html = (tmp_path / "changes.html").read_text()
    payload = json.loads((tmp_path / "data/changes.json").read_text())
    assert "<script>alert" not in html
    assert payload["revisions"][0]["event"]["source_text"] == '<script>alert("revision")</script>'
    assert payload["revisions"][0]["display_type"] == "changed"
    assert payload["revisions"][0]["anchor"].startswith("change-")
    assert changelog_revisions(revisions)[0]["anchor"] == payload["revisions"][0]["anchor"]
