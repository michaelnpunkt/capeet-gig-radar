from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date
from hashlib import sha256
from typing import Any


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split()).strip()


def normalize_key(value: str) -> str:
    folded = unicodedata.normalize("NFKD", normalize_text(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", folded.casefold()).strip()


@dataclass(slots=True)
class Artist:
    name: str
    country: str | None = None
    link: str | None = None

    def __post_init__(self) -> None:
        self.name = normalize_text(self.name)


@dataclass(slots=True)
class Link:
    label: str
    url: str

    def __post_init__(self) -> None:
        self.label = normalize_text(self.label) or "Details"


@dataclass(slots=True)
class Genre:
    family: str = "Unklassifiziert"
    subgenres: list[str] = field(default_factory=list)
    source: str = "unclassified"

    def __post_init__(self) -> None:
        self.subgenres = list(dict.fromkeys(normalize_text(value) for value in self.subgenres if normalize_text(value)))[:3]


def stable_event_id(event_date: date, artists: list[Artist], venue: str, city: str) -> str:
    headliner = artists[0].name if artists else ""
    identity = "|".join((event_date.isoformat(), normalize_key(headliner), normalize_key(venue), normalize_key(city)))
    return sha256(identity.encode()).hexdigest()[:20]


@dataclass(slots=True)
class Event:
    event_date: date
    artists: list[Artist]
    title: str | None
    venue: str
    city: str
    state: str
    postal_code: str | None
    status: str
    links: list[Link]
    source_text: str
    id: str = ""
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    changed_at: str | None = None
    revision: int = 0
    baseline: bool = False
    active: bool = True
    genre: Genre = field(default_factory=Genre)

    def __post_init__(self) -> None:
        self.artists = [value if isinstance(value, Artist) else Artist(**value) for value in self.artists]
        self.links = [value if isinstance(value, Link) else Link(**value) for value in self.links]
        if not isinstance(self.genre, Genre):
            self.genre = Genre(**self.genre)
        self.title = normalize_text(self.title) if self.title else None
        self.venue = normalize_text(self.venue)
        self.city = normalize_text(self.city)
        self.source_text = normalize_text(self.source_text)
        self.status = self.status.casefold()
        if not self.id:
            self.id = stable_event_id(self.event_date, self.artists, self.venue, self.city)

    @property
    def headliner(self) -> str:
        return self.artists[0].name if self.artists else ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["event_date"] = self.event_date.isoformat()
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Event:
        data = dict(value)
        data["event_date"] = date.fromisoformat(data["event_date"])
        return cls(**data)
