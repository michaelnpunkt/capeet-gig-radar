from __future__ import annotations

import json

import pytest
import requests

from src.fetch import FetchError, fetch_text


class Session:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.headers = response, error, None

    def get(self, url, headers, timeout):
        self.headers = headers
        if self.error:
            raise self.error
        return self.response


def response(status=200, body=b"ok", headers=None):
    result = requests.Response()
    result.status_code, result._content, result.url, result.encoding = status, body, "https://www.capeet.com/gigs_list.html", "utf-8"
    result.headers.update(headers or {})
    return result


def test_conditional_headers_and_deferred_validators(tmp_path):
    state = tmp_path / "source-state.json"
    state.write_text(json.dumps({"etag": '"abc"', "last_modified": "yesterday"}), encoding="utf-8")
    session = Session(response(200, b"<html>x</html>", {"ETag": '"def"', "Last-Modified": "today"}))
    result = fetch_text("https://example.test", state, timeout=2, user_agent="agent", session=session)
    assert session.headers["If-None-Match"] == '"abc"'
    assert session.headers["If-Modified-Since"] == "yesterday"
    assert result.validators["etag"] == '"def"'
    assert json.loads(state.read_text())["etag"] == '"abc"'


def test_304_and_http_failures(tmp_path):
    result = fetch_text("https://example.test", tmp_path / "none", timeout=2, user_agent="agent", session=Session(response(304, b"")))
    assert not result.modified and result.content is None
    with pytest.raises(FetchError, match="HTTP-Status"):
        fetch_text("https://example.test", tmp_path / "none", timeout=2, user_agent="agent", session=Session(response(500)))
    with pytest.raises(FetchError, match="Abruf"):
        fetch_text("https://example.test", tmp_path / "none", timeout=2, user_agent="agent", session=Session(error=requests.ConnectionError("down")))
