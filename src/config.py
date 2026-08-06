from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class Settings:
    source_url: str = "https://www.capeet.com/gigs_list.html"
    project_url: str = "https://github.com/michaelnpunkt/capeet-gig-radar"
    site_url: str = "https://michaelnpunkt.github.io/capeet-gig-radar"
    data_dir: Path = ROOT / "data"
    output_dir: Path = ROOT / "docs"
    timeout_seconds: float = 30.0
    user_agent: str = "capeet-gig-radar/1.0 (+https://github.com/michaelnpunkt/capeet-gig-radar)"
    minimum_events: int = 20
    maximum_drop_ratio: float = 0.40
    past_event_retention_days: int = 120
    feed_days: int = 90
    feed_limit: int = 100
    musicbrainz_interval_seconds: float = 1.0
    musicbrainz_limit: int = 25

    @classmethod
    def from_env(cls) -> Settings:
        defaults = cls()
        return cls(
            source_url=os.getenv("CAPEET_SOURCE_URL", defaults.source_url),
            project_url=os.getenv("PROJECT_URL", defaults.project_url).rstrip("/"),
            site_url=os.getenv("SITE_URL", defaults.site_url).rstrip("/"),
            data_dir=Path(os.getenv("DATA_DIR", defaults.data_dir)),
            output_dir=Path(os.getenv("OUTPUT_DIR", defaults.output_dir)),
            minimum_events=int(os.getenv("MINIMUM_EVENTS", defaults.minimum_events)),
            maximum_drop_ratio=float(os.getenv("MAXIMUM_DROP_RATIO", defaults.maximum_drop_ratio)),
        )
