from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from src.guardrails import GuardrailError, validate_update
from src.history import reconcile
from src.models import stable_event_id


NOW = datetime(2027, 8, 1, tzinfo=timezone.utc)


def test_baseline_new_change_and_identical_second_run(fixture_events):
    baseline, revisions = reconcile(fixture_events, [], [], now=NOW, initial_baseline=True)
    assert all(event.baseline and event.revision == 0 for event in baseline)
    assert revisions == []
    identical, revisions = reconcile(deepcopy(fixture_events), baseline, revisions, now=NOW)
    assert revisions == [] and all(event.revision == 0 for event in identical)
    changed_source = deepcopy(fixture_events)
    changed_source[0].artists.append(deepcopy(changed_source[1].artists[0]))
    changed, revisions = reconcile(changed_source, baseline, revisions, now=NOW)
    assert changed[0].id == baseline[0].id
    assert changed[0].revision == 1 and revisions[-1]["kind"] == "changed"
    new_event = deepcopy(fixture_events[0])
    new_event.id = "new-event"
    new_event.event_date = new_event.event_date.replace(day=30)
    events, revisions = reconcile(fixture_events + [new_event], baseline, revisions, now=NOW)
    discovered = next(event for event in events if event.id == "new-event")
    assert not discovered.baseline and discovered.revision == 1


def test_missing_future_event_becomes_unlisted_not_cancelled(fixture_events):
    baseline, _ = reconcile(fixture_events, [], [], now=NOW, initial_baseline=True)
    events, revisions = reconcile(fixture_events[1:], baseline, [], now=NOW)
    missing = next(event for event in events if event.id == baseline[0].id)
    assert not missing.active and missing.status != "cancelled"
    assert revisions[-1]["kind"] == "unlisted"


def test_corrected_derived_year_preserves_existing_event_identity(fixture_events):
    old = fixture_events[0]
    old.event_date = old.event_date.replace(year=2026)
    old.id = stable_event_id(old.event_date, old.artists, old.venue, old.city)
    corrected = deepcopy(old)
    corrected.event_date = corrected.event_date.replace(year=2027)
    corrected.id = stable_event_id(corrected.event_date, corrected.artists, corrected.venue, corrected.city)
    assert corrected.id != old.id
    events, revisions = reconcile([corrected], [old], [], now=NOW)
    assert events[0].id == old.id
    assert revisions[0]["changes"]["event_date"] == {"from": "2026-09-01", "to": "2027-09-01"}


def test_country_link_source_and_enrichment_changes_are_not_revisions(fixture_events):
    baseline, _ = reconcile(fixture_events, [], [], now=NOW, initial_baseline=True)
    current = deepcopy(fixture_events)
    current[0].artists[0].name = f"{current[0].artists[0].name} (aut/d)"
    current[0].artists[0].country = None
    current[0].artists[0].link = "https://example.test/new"
    current[0].state = "Tirol"
    current[0].source_text = "Kosmetisch anders"
    events, revisions = reconcile(current, baseline, [], now=NOW)
    assert revisions == []
    assert events[0].revision == 0 and events[0].changed_at is None
    assert events[0].artists[0].link == "https://example.test/new"


def test_only_significant_event_changes_are_recorded(fixture_events):
    baseline, _ = reconcile(fixture_events, [], [], now=NOW, initial_baseline=True)
    current = deepcopy(fixture_events)
    current[0].event_date = current[0].event_date.replace(day=2)
    current[0].artists.append(deepcopy(current[1].artists[0]))
    current[0].venue = "Neues Flex"
    current[0].city = "Graz"
    current[0].status = "cancelled"
    _events, revisions = reconcile(current, baseline, [], now=NOW)
    assert set(revisions[0]["changes"]) == {"event_date", "artists", "venue", "city", "status"}
    assert revisions[0]["changes"]["artists"]["to"][-1] == {"name": current[1].artists[0].name}


def test_guardrails_minimum_drop_and_duplicates(fixture_events):
    with pytest.raises(GuardrailError, match="mindestens"):
        validate_update(fixture_events[:19], [], 20, .4)
    with pytest.raises(GuardrailError, match="fiel"):
        validate_update(fixture_events[:10], fixture_events, 1, .4)
    with pytest.raises(GuardrailError, match="Doppelte"):
        validate_update([fixture_events[0], deepcopy(fixture_events[0])], [], 1, .4)
