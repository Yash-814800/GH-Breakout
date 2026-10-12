from __future__ import annotations

from datetime import datetime

import httpx
import pytest

from breakout.enrich.stargazers import GitHubClient, RepoGone


def _star(uid: int, ts: str) -> dict:
    return {"starred_at": ts, "user": {"id": uid}}


def _client(handler) -> GitHubClient:
    return GitHubClient("tok", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_requires_token() -> None:
    with pytest.raises(ValueError):
        GitHubClient("")


def test_uses_repo_id_endpoint_star_accept_and_follows_pages() -> None:
    seen: list[httpx.Request] = []
    pages = {
        "1": [_star(1, "2026-09-01T00:00:00Z"), _star(2, "2026-09-02T00:00:00Z")],
        "2": [_star(3, "2026-09-03T12:00:00Z")],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        page = request.url.params.get("page", "1")
        link = '<https://api.github.com/repositories/42/stargazers?per_page=100&page=2>; rel="last"'
        return httpx.Response(200, json=pages[page], headers={"link": link})

    stars = list(_client(handler).stargazers(42))
    assert [s.user_id for s in stars] == [1, 2, 3]
    assert stars[2].starred_at == datetime(2026, 9, 3, 12)
    assert seen[0].url.path == "/repositories/42/stargazers"
    assert seen[0].headers["accept"] == "application/vnd.github.star+json"
    assert seen[0].headers["authorization"] == "Bearer tok"


def test_since_walks_backwards_from_last_page_and_stops() -> None:
    calls: list[str] = []
    pages = {
        "1": [_star(1, "2026-01-01T00:00:00Z")],
        "2": [_star(2, "2026-02-01T00:00:00Z")],
        "3": [_star(3, "2026-09-10T00:00:00Z")],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page", "1")
        calls.append(page)
        link = '<https://x/?page=3>; rel="last"'
        return httpx.Response(200, json=pages[page], headers={"link": link})

    got = list(_client(handler).stargazers(7, since=datetime(2026, 9, 1)))
    assert [s.user_id for s in got] == [3, 2]  # page 3, then page 2 (older: stop)
    assert calls == ["1", "3", "2"]  # first page probe, then backwards until older than `since`


def test_forbidden_is_repo_gone() -> None:
    c = _client(lambda r: httpx.Response(403, json={"message": "nope"}))
    with pytest.raises(RepoGone):
        list(c.stargazers(1))
