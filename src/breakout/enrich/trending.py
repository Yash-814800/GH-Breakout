"""GitHub Trending history (phase 4.4, ADR-018).

Sources (all MIT-licensed, see ADR-018):
- ``hf_top_projects``: HF dataset ``ronantakizawa/github-top-projects`` ``full/data.csv`` (daily
  all-languages lists scraped from Wayback Machine snapshots, 2013-08..2025-11-30);
- ``antonkomarev``: git repo ``antonkomarev/github-trending-archive`` (daily JSON per language,
  ``language`` null = all languages; ordered lists, rank = position);
- ``larsbijl``: git repo ``larsbijl/trending_archive`` (daily markdown, per-language sections).
- ``github_trending``: our own once-a-day fetch of ``/trending?since=daily`` (robots.txt checked).

Output ``trending.parquet (date, rank, repo_name, language_filter, source, repo_id)``;
``language_filter`` is NULL for the all-languages list. ``repo_id`` is resolved with
``resolve_repo_ids(name, date)`` and is NULL when the name never appears in the star history.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import urllib.robotparser
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from breakout.config import Config
from breakout.enrich import names as names_mod
from breakout.enrich.common import connect_limited, enrich_dir, sql_str
from breakout.logging import get_logger
from breakout.paths import DATA_DIR, ensure_dir

log = get_logger(__name__)

TRENDING = "trending.parquet"
HF_DATASET = "ronantakizawa/github-top-projects"
GIT_SOURCES = {
    "antonkomarev": "https://github.com/antonkomarev/github-trending-archive.git",
    "larsbijl": "https://github.com/larsbijl/trending_archive.git",
}
TRENDING_URL = "https://github.com/trending?since=daily"

SCHEMA = pa.schema(
    [
        ("date", pa.date32()),
        ("rank", pa.int32()),
        ("repo_name", pa.string()),
        ("language_filter", pa.string()),
        ("source", pa.string()),
        ("repo_id", pa.int64()),
    ]
)

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+$")


def valid_name(name: str | None) -> bool:
    return bool(name and _NAME.match(name))


def src_dir() -> Path:
    return ensure_dir(DATA_DIR / "tmp" / "trending_src")


# ---- parsers (pure) ----------------------------------------------------------------------------


def parse_hf_full_csv(path: Path) -> Iterator[dict[str, Any]]:
    """Rows of ``full/data.csv`` (``name, star_count, fork_count, repo_owner, rank, date``)."""
    with open(path, newline="", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            full = f"{rec['repo_owner']}/{rec['name']}"
            try:
                d = date.fromisoformat(rec["date"])
                rank = int(rec["rank"])
            except (ValueError, KeyError):
                continue
            if valid_name(full):
                yield {
                    "date": d,
                    "rank": rank,
                    "repo_name": full,
                    "language_filter": None,
                    "source": "hf_top_projects",
                }


def parse_antonkomarev_json(text: str) -> Iterator[dict[str, Any]]:
    """One ``archive/repository/YYYY/YYYY-MM-DD/<language>.json`` file."""
    doc = json.loads(text)
    d = date.fromisoformat(doc["date"])
    lang = doc.get("language")
    for i, name in enumerate(doc.get("list") or [], 1):
        if valid_name(name):
            yield {
                "date": d,
                "rank": i,
                "repo_name": name,
                "language_filter": lang.lower() if lang else None,
                "source": "antonkomarev",
            }


_MD_LANG = re.compile(r"^#{3,5}\s*([^\s#].*?)\s*$")
_MD_ITEM = re.compile(r"^\*\s*\[([^\]]+)\]\(https://github\.com/([^)\s]+)\)")


def parse_larsbijl_md(text: str, day: date) -> Iterator[dict[str, Any]]:
    """One full ``YYYY-MM-DD.md`` file: ``#### <language>`` headings, then ``* [name](url)``."""
    lang: str | None = None
    rank = 0
    for line in text.splitlines():
        line = line.rstrip()
        m = _MD_ITEM.match(line)
        if m and lang is not None:
            rank += 1
            name = m.group(2).strip("/")
            if valid_name(name):
                yield {
                    "date": day,
                    "rank": rank,
                    "repo_name": name,
                    "language_filter": lang,
                    "source": "larsbijl",
                }
            continue
        h = _MD_LANG.match(line)
        if h and not line.startswith("### 20") and not re.match(r"^#{3}\s*\d{4}-", line):
            lang, rank = h.group(1).lower(), 0


_ARTICLE = re.compile(r"<article[^>]*class=\"[^\"]*Box-row[^\"]*\"[^>]*>(.*?)</article>", re.S)
_H2_HREF = re.compile(r"<h2[^>]*>.*?<a[^>]*href=\"/([^\"/?#]+/[^\"/?#]+)\"", re.S)


def parse_trending_html(html: str) -> list[str]:
    """Repo ``owner/name`` strings in page order from the trending page."""
    out = []
    for art in _ARTICLE.findall(html):
        m = _H2_HREF.search(art)
        if m and valid_name(m.group(1)):
            out.append(m.group(1))
    return out


def robots_allows(robots_txt: str, url: str = TRENDING_URL, agent: str = "gh-breakout") -> bool:
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(robots_txt.splitlines())
    return rp.can_fetch(agent, url)


# ---- acquisition -------------------------------------------------------------------------------


def sync_git_source(name: str) -> Path:
    """Shallow clone (or fast-forward) one archive repo into the scratch area."""
    dest = src_dir() / name
    if (dest / ".git").exists():
        subprocess.run(
            ["git", "-C", str(dest), "pull", "-q", "--ff-only", "--depth", "1"], check=True
        )
    else:
        subprocess.run(
            ["git", "clone", "-q", "--depth", "1", GIT_SOURCES[name], str(dest)], check=True
        )
    return dest


def fetch_hf_csv() -> Path:
    import os

    os.environ.setdefault("HF_HOME", str(DATA_DIR / "hf_home"))
    from huggingface_hub import hf_hub_download

    return Path(
        hf_hub_download(
            HF_DATASET, "full/data.csv", repo_type="dataset", local_dir=str(src_dir() / "hf")
        )
    )


def iter_antonkomarev(root: Path) -> Iterator[dict[str, Any]]:
    for f in sorted((root / "archive" / "repository").glob("*/*/*.json")):
        try:
            yield from parse_antonkomarev_json(f.read_text(encoding="utf-8"))
        except (ValueError, KeyError) as exc:
            log.warning("skip %s: %s", f, exc)


def iter_larsbijl(root: Path) -> Iterator[dict[str, Any]]:
    for f in sorted(root.glob("20*/*/20??-??-??.md")) + sorted(root.glob("20??-??/20??-??-??.md")):
        try:
            day = date.fromisoformat(f.stem)
        except ValueError:
            continue
        yield from parse_larsbijl_md(f.read_text(encoding="utf-8"), day)


# ---- build -------------------------------------------------------------------------------------


def _write_rows(con: duckdb.DuckDBPyConnection, rows: Iterable[dict[str, Any]], table: str) -> int:
    t = pa.Table.from_pylist(
        [{**{k: r.get(k) for k in SCHEMA.names if k != "repo_id"}} for r in rows],
        schema=pa.schema([f for f in SCHEMA if f.name != "repo_id"]),
    )
    con.register("_rows_arrow", t)
    con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM _rows_arrow")
    con.unregister("_rows_arrow")
    return t.num_rows


def build_trending(cfg: Config, rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Union ``rows``, dedupe, resolve repo ids and write ``trending.parquet`` atomically."""
    hist = names_mod.history_path(cfg)
    if not hist.exists():
        raise FileNotFoundError("repo_name_history.parquet missing; run `breakout enrich names`")
    con = connect_limited()
    try:
        n = _write_rows(con, rows, "raw")
        con.execute(
            """CREATE TABLE q AS
               SELECT DISTINCT date, rank, repo_name, language_filter, source FROM raw"""
        )
        con.execute("CREATE TABLE names AS SELECT DISTINCT repo_name AS name, date AS as_of FROM q")
        names_mod.resolve_repo_ids(con, "names", hist).create("resolved")
        dest = enrich_dir(cfg) / TRENDING
        ensure_dir(dest.parent)
        tmp = dest.with_suffix(".tmp")
        con.execute(
            f"""COPY (
                  SELECT q.date, q.rank, q.repo_name, q.language_filter, q.source,
                         r.repo_id::BIGINT AS repo_id
                  FROM q LEFT JOIN resolved r ON r.name = q.repo_name AND r.as_of = q.date
                  ORDER BY q.date, q.source, q.language_filter NULLS FIRST, q.rank, q.repo_name
                ) TO {sql_str(tmp)} (FORMAT PARQUET, COMPRESSION ZSTD)"""
        )
        tmp.replace(dest)
        out = con.execute(
            f"""SELECT count(*), count(repo_id), count(DISTINCT date), min(date), max(date)
                FROM read_parquet({sql_str(dest)})"""
        ).fetchone()
    finally:
        con.close()
    assert out is not None
    return {
        "input_rows": n,
        "rows": out[0],
        "resolved": out[1],
        "days": out[2],
        "first": str(out[3]),
        "last": str(out[4]),
    }


def existing_today_rows(cfg: Config) -> list[dict[str, Any]]:
    p = enrich_dir(cfg) / TRENDING
    if not p.exists():
        return []
    return [r for r in pq.read_table(p).to_pylist() if r["source"] == "github_trending"]


def history_rows(cfg: Config) -> Iterator[dict[str, Any]]:
    yield from parse_hf_full_csv(fetch_hf_csv())
    yield from iter_antonkomarev(sync_git_source("antonkomarev"))
    yield from iter_larsbijl(sync_git_source("larsbijl"))
    yield from existing_today_rows(cfg)


def trending_today(cfg: Config, client: httpx.Client, today: date) -> list[dict[str, Any]]:
    """Fetch today's all-languages list once (robots.txt checked first). Returns ``[]`` when
    robots disallow, so the caller can fall back to the archives (ADR-018)."""
    robots = client.get("https://github.com/robots.txt")
    robots.raise_for_status()
    if not robots_allows(robots.text, TRENDING_URL, "gh-breakout"):
        log.warning("robots.txt disallows /trending; not fetching")
        return []
    r = client.get(TRENDING_URL)
    r.raise_for_status()
    return [
        {
            "date": today,
            "rank": i,
            "repo_name": n,
            "language_filter": None,
            "source": "github_trending",
        }
        for i, n in enumerate(parse_trending_html(r.text), 1)
    ]


def coverage_by_month(cfg: Config) -> list[tuple[str, int, int]]:
    """``(YYYY-MM, days with >= 1 entry, days with an all-languages entry)`` per month."""
    con = connect_limited()
    try:
        return [
            (r[0], r[1], r[2])
            for r in con.execute(
                f"""SELECT strftime(date, '%Y-%m') m, count(DISTINCT date),
                           count(DISTINCT date) FILTER (language_filter IS NULL)
                    FROM read_parquet({sql_str(enrich_dir(cfg) / TRENDING)})
                    GROUP BY 1 ORDER BY 1"""
            ).fetchall()
        ]
    finally:
        con.close()
