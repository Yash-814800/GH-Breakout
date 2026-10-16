from __future__ import annotations

import httpx
import pytest

from breakout.enrich import http as H


def test_throttle_spaces_calls() -> None:
    clk = H.FakeClock()
    t = H.Throttle(1.0, clk)
    t.wait()
    t.wait()
    t.wait()
    assert clk.sleeps == [1.0, 1.0]


def test_rest_wait_low_remaining_sleeps_to_reset() -> None:
    now = 1000.0
    assert (
        H.rest_wait_seconds({"x-ratelimit-remaining": "5", "x-ratelimit-reset": "1060"}, now)
        == 61.0
    )
    assert (
        H.rest_wait_seconds({"x-ratelimit-remaining": "4000", "x-ratelimit-reset": "1060"}, now)
        == 0
    )
    assert H.rest_wait_seconds({"retry-after": "30"}, now) == 31.0
    # reset in the past: only the 1 s slack
    assert (
        H.rest_wait_seconds({"x-ratelimit-remaining": "0", "x-ratelimit-reset": "900"}, now) == 1.0
    )
    # capped at one hour plus slack
    assert (
        H.rest_wait_seconds({"x-ratelimit-remaining": "0", "x-ratelimit-reset": "99999"}, now)
        == H.MAX_SLEEP
    )


def test_graphql_wait() -> None:
    now = 1_700_000_000.0
    reset = "2023-11-14T22:14:20Z"  # = 1_700_000_060
    assert H.graphql_wait_seconds({"remaining": 10, "resetAt": reset}, now) == 61.0
    assert H.graphql_wait_seconds({"remaining": 5000, "resetAt": reset}, now) == 0.0
    assert H.graphql_wait_seconds(None, now) == 0.0


def test_token_only_sent_to_github_api_and_not_in_repr() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={})

    clk = H.FakeClock()
    client = H.make_client("https://example.test/r", transport=httpx.MockTransport(handler))
    api = H.GitHubApi("sekret", client=client, clock=clk)
    api.rest_get("/user/1")
    api.rest_get("https://example.com/other")
    assert seen[0].headers["authorization"] == "Bearer sekret"
    assert "authorization" not in seen[1].headers
    assert "sekret" not in repr(api)
    assert seen[0].headers["user-agent"].startswith("gh-breakout (+")


def test_retries_5xx_and_secondary_rate_limit_with_fake_clock() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(502)
        if calls["n"] == 2:
            return httpx.Response(403, headers={"retry-after": "20"})
        return httpx.Response(200, json={"ok": True})

    clk = H.FakeClock()
    api = H.GitHubApi(
        "t", client=H.make_client("u", transport=httpx.MockTransport(handler)), clock=clk
    )
    r = api.rest_get("/x")
    assert r.json() == {"ok": True}
    assert calls["n"] == 3 and api.requests == 3
    assert 21.0 in clk.sleeps  # retry-after honoured on the fake clock, no real waiting


def test_requires_token() -> None:
    with pytest.raises(ValueError):
        H.GitHubApi("", client=H.make_client("u"))
