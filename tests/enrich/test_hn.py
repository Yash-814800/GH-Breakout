from __future__ import annotations

from datetime import datetime
from pathlib import Path

import httpx
import pytest

from breakout.config import load_config
from breakout.enrich import hn
from breakout.enrich.http import FakeClock, make_client

CASES = [
    ("https://github.com/torvalds/linux", "torvalds/linux"),
    ("http://github.com/torvalds/linux", "torvalds/linux"),
    ("https://www.github.com/torvalds/linux", "torvalds/linux"),
    ("github.com/torvalds/linux", "torvalds/linux"),
    ("https://github.com/torvalds/linux/", "torvalds/linux"),
    ("https://github.com/torvalds/linux.git", "torvalds/linux"),
    ("https://github.com/torvalds/linux?tab=readme-ov-file", "torvalds/linux"),
    ("https://github.com/torvalds/linux#readme", "torvalds/linux"),
    ("https://github.com/torvalds/linux/issues/123", "torvalds/linux"),
    ("https://github.com/torvalds/linux/blob/master/README.md", "torvalds/linux"),
    ("https://github.com/Torvalds/Linux", "Torvalds/Linux"),
    ("https://github.com/a-b/c.d_e", "a-b/c.d_e"),
    ("https://github.com/user", None),
    ("https://github.com/", None),
    ("https://github.com/orgs/microsoft/people", None),
    ("https://github.com/topics/python", None),
    ("https://github.com/sponsors/someone", None),
    ("https://github.com/marketplace/actions/foo", None),
    ("https://github.com/features/copilot", None),
    ("https://gist.github.com/user/abc123", None),
    ("https://raw.githubusercontent.com/user/repo/main/x.py", None),
    ("https://user.github.io/repo", None),
    ("https://github.com.evil.example/user/repo", None),
    ("https://notgithub.com/user/repo", None),
    ("https://gitlab.com/user/repo", None),
    ("", None),
    (None, None),
    ("https://github.com/-bad/repo", None),
    ("https://github.com/user/repo with space", None),
]


@pytest.mark.parametrize(("url", "expected"), CASES)
def test_parse_github_repo_url(url: str | None, expected: str | None) -> None:
    assert hn.parse_github_repo_url(url) == expected


def test_case_count() -> None:
    assert len(CASES) >= 20


def _hit(i: int, ts: int) -> dict:
    return {
        "objectID": str(i),
        "created_at_i": ts,
        "points": 5,
        "num_comments": 1,
        "title": f"t{i}",
        "url": f"https://github.com/o/r{i}",
    }


def test_adaptive_windows_halve_until_under_cap() -> None:
    calls: list[tuple[int, int]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        f = req.url.params["numericFilters"]
        a, b = (int(x.split(">=")[-1].split("<")[-1]) for x in f.split(","))
        calls.append((a, b))
        span = b - a
        n = 1000 if span > 4 * 86400 else 10  # only windows <= 4 days fit under the cap
        return httpx.Response(200, json={"nbHits": n, "hits": [_hit(a, a)]})

    client = hn.HnClient(
        make_client("u", transport=httpx.MockTransport(handler)), clock=FakeClock()
    )
    got: list[tuple[int, int]] = []
    hn.fetch_adaptive(client, hn.Window(0, 7 * 86400), lambda w, b: got.append((w.start, w.end)))
    assert got == [(0, 3 * 86400 + 43200), (3 * 86400 + 43200, 7 * 86400)]
    assert calls[0] == (0, 7 * 86400)


def test_collect_is_resumable(tmp_path: Path, write_config) -> None:
    def mutate(d: dict) -> None:
        d["enrich"]["output_dir"] = str(tmp_path / "enrich")

    cfg = load_config(write_config(mutate))
    n = {"calls": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        n["calls"] += 1
        a = int(req.url.params["numericFilters"].split(",")[0].split(">=")[1])
        return httpx.Response(200, json={"nbHits": 1, "hits": [_hit(a // 86400 + 1, a + 5)]})

    def run() -> dict:
        c = hn.HnClient(make_client("u", transport=httpx.MockTransport(handler)), clock=FakeClock())
        return hn.collect(cfg, c, datetime(2020, 1, 1).date(), datetime(2020, 1, 22))

    first = run()
    assert first["fetched_windows"] == 3 and first["stories_raw"] == 3
    calls_after_first = n["calls"]
    second = run()
    assert second["fetched_windows"] == 0 and second["skipped_windows"] == 3
    assert n["calls"] == calls_after_first
