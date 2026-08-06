from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from .models import Artist, Event, Link, normalize_text


class ParseError(ValueError):
    pass


DATE_START = re.compile(r"^\s*(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.\s*:\s*")
YEAR = re.compile(r"\b(20\d{2})\b")
YEAR_LINE = re.compile(r"^\s*\[?(20\d{2})\]?\s*:?\s*$")
COUNTRY = re.compile(r"\s*\(([A-Z]{1,3}(?:/[A-Z]{1,3})*)\)\s*$", re.I)
ARTIST_SEPARATOR = re.compile(r"\s+(?:/|\+)\s+")
POSTAL_CITY = re.compile(r"(?:^|[,;/]\s*)?(?P<postal>\d{4})\s+(?P<city>[^,;/]+)\s*$")
CANCELLED = ("abgesagt", "abges.", "cancelled", "canceled", "entfällt", "entfaellt")
POSTPONED = ("verschoben", "verlegt", "postponed")


@dataclass(slots=True)
class Token:
    text: str
    bold: bool = False
    italic: bool = False
    href: str | None = None
    red: bool = False


def _safe_url(value: str | None, base_url: str) -> str | None:
    if not value:
        return None
    resolved = urljoin(base_url, value.strip())
    return resolved if urlparse(resolved).scheme in {"http", "https"} else None


def _lines(html: str, base_url: str) -> list[tuple[int | None, list[Token]]]:
    soup = BeautifulSoup(html, "html5lib")
    root = soup.body or soup
    result: list[tuple[int | None, list[Token]]] = []
    line: list[Token] = []
    title_text = soup.title.get_text(" ", strip=True) if soup.title else ""
    early_text = root.get_text(" ", strip=True)[:1000]
    initial_year = YEAR.search(f"{title_text} {early_text}")
    year: int | None = int(initial_year.group(1)) if initial_year else None

    def finish() -> None:
        nonlocal line
        if normalize_text("".join(token.text for token in line)):
            result.append((year, line))
        line = []

    for node in root.descendants:
        if isinstance(node, Tag):
            if node.name == "br":
                finish()
            elif node.name in {"h1", "h2", "h3", "h4"}:
                finish()
                match = YEAR.search(node.get_text(" ", strip=True))
                if match:
                    year = int(match.group(1))
            continue
        if not isinstance(node, NavigableString):
            continue
        parents = list(node.parents)
        if any(parent.name in {"script", "style", "h1", "h2", "h3", "h4"} for parent in parents):
            continue
        anchor = next((parent for parent in parents if parent.name == "a"), None)
        styled = [parent for parent in parents if isinstance(parent, Tag)]
        color = " ".join(str(parent.get("color", "")) + " " + str(parent.get("style", "")) for parent in styled)
        line.append(Token(
            str(node),
            any(parent.name in {"b", "strong"} for parent in parents),
            any(parent.name in {"i", "em"} for parent in parents),
            _safe_url(str(anchor.get("href", "")), base_url) if anchor else None,
            bool(re.search(r"(?:#?f{2}0{4}|red)", color, re.I)),
        ))
    finish()
    return result


def _trim_date(tokens: list[Token], count: int) -> list[Token]:
    result: list[Token] = []
    for token in tokens:
        if count >= len(token.text):
            count -= len(token.text)
        else:
            result.append(Token(token.text[count:], token.bold, token.italic, token.href, token.red))
            count = 0
    return result


def _split_at(tokens: list[Token]) -> tuple[list[Token], list[Token]]:
    before: list[Token] = []
    after: list[Token] = []
    found = False
    for token in tokens:
        if not found and "@" in token.text:
            left, right = token.text.split("@", 1)
            if left:
                before.append(Token(left, token.bold, token.italic, token.href, token.red))
            if right:
                after.append(Token(right, token.bold, token.italic, token.href, token.red))
            found = True
        elif found:
            after.append(token)
        else:
            before.append(token)
    if not found:
        raise ParseError("Ortstrenner @ fehlt")
    return before, after


def _artists(tokens: list[Token]) -> list[Artist]:
    artists: list[Artist] = []
    current: list[Token] = []
    groups: list[list[Token]] = []
    for token in tokens:
        if token.bold:
            current.append(token)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    for group in groups:
        segments: list[list[Token]] = [[]]
        for token in group:
            parts = ARTIST_SEPARATOR.split(token.text)
            separators = list(ARTIST_SEPARATOR.finditer(token.text))
            for index, part in enumerate(parts):
                if part:
                    segments[-1].append(Token(part, token.bold, token.italic, token.href, token.red))
                if index < len(separators):
                    segments.append([])
        for segment in segments:
            raw = normalize_text("".join(token.text for token in segment)).strip(" ,+&/")
            country_match = COUNTRY.search(raw)
            name = COUNTRY.sub("", raw).strip(" ,+&/")
            if name:
                country = country_match.group(1).upper() if country_match else None
                artists.append(Artist(name, country, next((token.href for token in segment if token.href), None)))
    return artists


def _parse_location(tokens: list[Token], source_location: str | None = None) -> tuple[str, str, str | None]:
    text = normalize_text(source_location or "".join(token.text for token in tokens))
    for keyword in CANCELLED + POSTPONED:
        text = re.sub(re.escape(keyword), "", text, flags=re.I)
    text = re.sub(r"(?:\s*\[[^\]]*\])+\s*$", "", text)
    text = normalize_text(text).strip(" ,;/|-–—")
    postal = POSTAL_CITY.search(text)
    if postal:
        venue = text[:postal.start()].strip(" ,;/|-–—")
        return venue, normalize_text(postal.group("city")).strip(" ,;/|-–—"), postal.group("postal")
    separator = r"\s*(?:,|;)\s*" if re.search(r"[,;]", text) else r"\s*/\s*"
    parts = [normalize_text(part) for part in re.split(separator, text) if normalize_text(part)]
    if len(parts) < 2:
        raise ParseError(f"Ort unvollständig: {text!r}")
    return " / ".join(parts[:-1]), parts[-1], None


def _parse_line(tokens: list[Token], year: int, prior_month: int | None) -> tuple[Event, int]:
    source_text = normalize_text("".join(token.text for token in tokens))
    match = DATE_START.match(source_text)
    if not match:
        raise ParseError("Keine Datumszeile")
    day, month = int(match.group("day")), int(match.group("month"))
    if prior_month is not None and prior_month >= 10 and month <= 3:
        year += 1
    remaining = _trim_date(tokens, match.end())
    before, after = _split_at(remaining)
    artists = _artists(before)
    if not artists:
        raise ParseError("Keine fett ausgezeichneten Künstler")
    festival = normalize_text(" ".join(token.text for token in before if token.italic)).strip(" ,;-–—") or None
    venue, city, postal_code = _parse_location(after, source_text.split("@", 1)[1])
    folded = source_text.casefold()
    status = "cancelled" if any(token.red for token in remaining) or any(word in folded for word in CANCELLED) else "postponed" if any(word in folded for word in POSTPONED) else "scheduled"
    links: list[Link] = []
    seen: set[str] = set()
    for token in remaining:
        if token.href and token.href not in seen:
            links.append(Link(normalize_text(token.text), token.href))
            seen.add(token.href)
    return Event(date(year, month, day), artists, festival, venue, city, "Unbekannt", postal_code, status, links, source_text), month


def parse_events(html: str, base_url: str) -> list[Event]:
    events: list[Event] = []
    errors: list[str] = []
    current_year: int | None = None
    prior_month: int | None = None
    for heading_year, tokens in _lines(html, base_url):
        text = normalize_text("".join(token.text for token in tokens))
        year_marker = YEAR_LINE.match(text)
        if year_marker:
            current_year = int(year_marker.group(1))
            prior_month = None
            continue
        if not DATE_START.match(text):
            continue
        if heading_year is not None and (current_year is None or heading_year > current_year):
            current_year, prior_month = heading_year, None
        if current_year is None:
            errors.append("Jahresüberschrift fehlt")
            continue
        try:
            event, prior_month = _parse_line(tokens, current_year, prior_month)
            current_year = event.event_date.year
            events.append(event)
        except (ParseError, ValueError) as error:
            errors.append(str(error))
    unique = {event.id: event for event in events}
    if not unique:
        detail = f" ({'; '.join(errors[:3])})" if errors else ""
        raise ParseError(f"Keine gültigen Veranstaltungen gefunden{detail}")
    return sorted(unique.values(), key=lambda event: (event.event_date, event.headliner.casefold()))
