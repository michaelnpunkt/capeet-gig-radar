from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from src.guardrails import GuardrailError, validate_update
from src.history import reconcile


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


def test_guardrails_minimum_drop_and_duplicates(fixture_events):
    with pytest.raises(GuardrailError, match="mindestens"):
        validate_update(fixture_events[:19], [], 20, .4)
    with pytest.raises(GuardrailError, match="fiel"):
        validate_update(fixture_events[:10], fixture_events, 1, .4)
    with pytest.raises(GuardrailError, match="Doppelte"):
        validate_update([fixture_events[0], deepcopy(fixture_events[0])], [], 1, .4)
