from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from breakout.enrich import trending as T

HTML = """
<article class="Box-row">
  <h2 class="h3 lh-condensed"><a href="/owner-a/repo.one" data-view-component="true">
      <span class="text-normal">owner-a /</span> repo.one</a></h2>
</article>
<article class="Box-row"><h2><a href="/b/two">b / two</a></h2></article>
<article class="Box-row"><h2><a href="/sponsors/x/y">bad</a></h2></article>
"""


def test_parse_trending_html() -> None:
    assert T.parse_trending_html(HTML) == ["owner-a/repo.one", "b/two"]


def test_parse_antonkomarev_json() -> None:
    txt = json.dumps({"date": "2026-10-15", "language": "Python", "list": ["a/b", "bad", "c/d"]})
    rows = list(T.parse_antonkomarev_json(txt))
    assert [(r["rank"], r["repo_name"], r["language_filter"]) for r in rows] == [
        (1, "a/b", "python"),
        (3, "c/d", "python"),
    ]
    all_lang = json.dumps({"date": "2026-10-15", "language": None, "list": ["x/y"]})
    assert next(T.parse_antonkomarev_json(all_lang))["language_filter"] is None


def test_parse_larsbijl_md_both_heading_styles() -> None:
    new = (
        "### 2026-10-15\n\n#### python\n* [a/b](https://github.com/a/b): desc\n"
        "* [c/d](https://github.com/c/d): x\n\n#### go\n* [e/f](https://github.com/e/f): y\n"
    )
    old = "###2016-03-15\n\n####python\n* [a/b](https://github.com/a/b): d\n"
    rows = list(T.parse_larsbijl_md(new, date(2026, 10, 15)))
    assert [(r["language_filter"], r["rank"], r["repo_name"]) for r in rows] == [
        ("python", 1, "a/b"),
        ("python", 2, "c/d"),
        ("go", 1, "e/f"),
    ]
    rows = list(T.parse_larsbijl_md(old, date(2016, 3, 15)))
    assert [(r["language_filter"], r["repo_name"]) for r in rows] == [("python", "a/b")]


def test_parse_hf_csv(tmp_path: Path) -> None:
    p = tmp_path / "d.csv"
    p.write_text(
        "name,star_count,fork_count,repo_owner,rank,date\n"
        "TrendRadar,32864,17842,sansan0,1,2025-11-30\n"
        "x,,,,2,2025-11-30\n"
        "y,1,1,o,notanint,2025-11-30\n"
    )
    rows = list(T.parse_hf_full_csv(p))
    assert len(rows) == 1 and rows[0]["repo_name"] == "sansan0/TrendRadar"
    assert rows[0]["date"] == date(2025, 11, 30) and rows[0]["language_filter"] is None


ROBOTS_OK = "User-agent: *\nDisallow: /*/*/pulse\nDisallow: /search$\n"
ROBOTS_BLOCK = "User-agent: *\nDisallow: /trending\n"
ROBOTS_ALL = "User-agent: gh-breakout\nDisallow: /\n"


@pytest.mark.parametrize(
    ("txt", "allowed"), [(ROBOTS_OK, True), (ROBOTS_BLOCK, False), (ROBOTS_ALL, False)]
)
def test_robots(txt: str, allowed: bool) -> None:
    assert T.robots_allows(txt) is allowed
