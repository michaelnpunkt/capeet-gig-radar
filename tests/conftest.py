from __future__ import annotations

from pathlib import Path

import pytest

from src.parser import parse_events


@pytest.fixture
def fixture_path() -> Path:
    return Path(__file__).parent / "fixtures/events.html"


@pytest.fixture
def fixture_events(fixture_path: Path):
    return parse_events(fixture_path.read_text(encoding="utf-8"), "https://source.example/gigs/")
