from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .persistence import load_json


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FetchResult:
    content: str | None
    status_code: int
    validators: dict[str, Any] | None

    @property
    def modified(self) -> bool:
        return self.status_code == 200


def fetch_text(url: str, state_path: Path, *, timeout: float, user_agent: str, session: requests.Session | None = None) -> FetchResult:
    state = load_json(state_path, {})
    headers = {"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"}
    if state.get("etag"):
        headers["If-None-Match"] = state["etag"]
    if state.get("last_modified"):
        headers["If-Modified-Since"] = state["last_modified"]
    try:
        response = (session or requests.Session()).get(url, headers=headers, timeout=timeout)
    except requests.RequestException as error:
        raise FetchError(f"Abruf fehlgeschlagen: {error}") from error
    if response.status_code == 304:
        return FetchResult(None, 304, None)
    if response.status_code != 200:
        raise FetchError(f"Unerwarteter HTTP-Status {response.status_code} für {url}")
    if not response.content.strip():
        raise FetchError("Quelle lieferte eine leere Antwort")
    response.encoding = response.encoding or "utf-8"
    return FetchResult(response.text, 200, {
        "etag": response.headers.get("ETag"),
        "last_modified": response.headers.get("Last-Modified"),
        "url": response.url,
    })
