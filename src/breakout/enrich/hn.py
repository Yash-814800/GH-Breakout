"""Hacker News stories linking to GitHub repos (phase 4.5, ADR-019).

Free Algolia HN search API, adaptive time windows (every window must return < 1000 hits, the API
cap), resumable by window. ``points`` and ``num_comments`` are values at fetch time: see the
leakage note in ``config/feature_dictionary.yaml`` / ADR-019.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from breakout.config import Config
from breakout.enrich import names as names_mod
from breakout.enrich.common import connect_limited, enrich_dir, sql_str
from breakout.enrich.http import Clock, SystemClock, Throttle
from breakout.logging import get_logger

log = get_logger(__name__)

API = "https://hn.algolia.com/api/v1/search_by_date"
HN_STORIES = "hn_stories.parquet"
HN_RAW = "hn_raw.parquet"
HN_WINDOWS = "hn_windows.parquet"
PAGE_CAP = 1000
MIN_WINDOW_SECONDS = 3600

RAW_SCHEMA = pa.schema(
    [
        ("story_id", pa.int64()),
        ("created_at", pa.timestamp("us")),
        ("points", pa.int32()),
        ("num_comments", pa.int32()),
        ("title", pa.string()),
        ("url", pa.string()),
        ("fetched_at", pa.timestamp("us")),
    ]
)
WINDOW_SCHEMA = pa.schema(
    [
        ("start_ts", pa.int64()),
        ("end_ts", pa.int64()),
        ("n_hits", pa.int32()),
        ("fetched_at", pa.timestamp("us")),
    ]
)

# first path segments of github.com that are not user/org names
RESERVED_OWNERS = frozenset(
    [
        "about",
        "account",
        "apps",
        "collections",
        "community",
        "contact",
        "customer-stories",
        "enterprise",
        "events",
        "explore",
        "features",
        "files",
        "gist",
        "git-guides",
        "github-copilot",
        "hovercards",
        "issues",
        "join",
        "login",
        "logout",
        "marketplace",
        "mobile",
        "new",
        "nonprofit",
        "notifications",
        "orgs",
        "organizations",
        "pricing",
        "pulls",
        "readme",
        "resources",
        "search",
        "security",
        "sessions",
        "settings",
        "site",
        "sponsors",
        "stars",
        "team",
        "topics",
        "trending",
        "users",
        "why",
        "partners",
        "codespaces",
        "copilot",
        "discussions",
        "education",
        "premium-support",
        "readme.md",
        "solutions",
    ]
)
_SEG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def parse_github_repo_url(url: str | None) -> str | None:
    """``https://github.com/<owner>/<repo>[/...]`` -> ``owner/repo`` (case kept); else None.

    Rejects non-github.com hosts (gist., raw., *.github.io), owner-only URLs and reserved owner
    paths (orgs, topics, sponsors, marketplace, ...). Strips ``.git``, queries and fragments.
    """
    if not url:
        return None
    u = url.strip()
    if "://" not in u:
        u = "https://" + u
    try:
        parts = urlsplit(u)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if host not in {"github.com", "www.github.com"}:
        return None
    segs = [unquote(s) for s in parts.path.split("/") if s]
    if len(segs) < 2:
        return None
    owner, repo = segs[0], segs[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if owner.lower() in RESERVED_OWNERS or not _SEG.match(owner) or not _SEG.match(repo):
        return None
    if owner.endswith(".") or repo in {".", ".."}:
        return None
    return f"{owner}/{repo}"


def _utc_naive(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, UTC).replace(tzinfo=None)


@dataclass
class Window:
    start: int
    end: int  # exclusive


class HnClient:
    def __init__(
        self, client: httpx.Client, *, max_rps: float = 1.0, clock: Clock | None = None
    ) -> None:
        self._client = client
        self.clock = clock or SystemClock()
        self._throttle = Throttle(max_rps, self.clock)
        self.requests = 0

    def fetch_window(self, w: Window) -> dict[str, Any]:
        params = {
            "tags": "story",
            "query": "github.com",
            "restrictSearchableAttributes": "url",
            "numericFilters": f"created_at_i>={w.start},created_at_i<{w.end}",
            "hitsPerPage": str(PAGE_CAP),
        }
        for attempt in range(6):
            self._throttle.wait()
            self.requests += 1
            try:
                r = self._client.get(API, params=params)
            except httpx.TransportError:
                self.clock.sleep(2.0**attempt)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                self.clock.sleep(min(2.0**attempt * 2, 60))
                continue
            r.raise_for_status()
            body: dict[str, Any] = r.json()
            return body
        raise RuntimeError(f"HN Algolia window {w} failed after retries")


def plan_windows(start: int, end: int, size: int) -> list[Window]:
    out, a = [], start
    while a < end:
        out.append(Window(a, min(a + size, end)))
        a += size
    return out


def fetch_adaptive(hn: HnClient, w: Window, sink: Callable[[Window, dict[str, Any]], None]) -> None:
    """Fetch ``w``; when ``nbHits >= 1000`` halve it (down to one hour) so no hit is cut off."""
    body = hn.fetch_window(w)
    n = int(body.get("nbHits", 0))
    if n >= PAGE_CAP and (w.end - w.start) > MIN_WINDOW_SECONDS:
        mid = w.start + (w.end - w.start) // 2
        fetch_adaptive(hn, Window(w.start, mid), sink)
        fetch_adaptive(hn, Window(mid, w.end), sink)
        return
    if n >= PAGE_CAP:
        log.warning("HN window %s-%s truncated at %d hits", w.start, w.end, n)
    sink(w, body)


def raw_rows(body: dict[str, Any], fetched_at: datetime) -> list[dict[str, Any]]:
    out = []
    for h in body.get("hits", []):
        try:
            sid = int(h["objectID"])
            created = _utc_naive(int(h["created_at_i"]))
        except (KeyError, ValueError, TypeError):
            continue
        out.append(
            {
                "story_id": sid,
                "created_at": created,
                "points": h.get("points"),
                "num_comments": h.get("num_comments"),
                "title": h.get("title"),
                "url": h.get("url"),
                "fetched_at": fetched_at,
            }
        )
    return out


def _read(path: Path, schema: pa.Schema) -> list[dict[str, Any]]:
    return pq.read_table(path).to_pylist() if path.exists() else []


def _write(path: Path, rows: list[dict[str, Any]], schema: pa.Schema) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), tmp, compression="zstd")
    tmp.replace(path)


def collect(
    cfg: Config,
    hn: HnClient,
    start: date,
    end: datetime,
    *,
    refetch_from: datetime | None = None,
    checkpoint_every: int = 40,
) -> dict[str, int]:
    """Fetch windows covering ``[start, end)``; completed windows (``hn_windows.parquet``) are
    skipped, except windows ending after ``refetch_from`` (recent stories keep gaining points)."""
    out = enrich_dir(cfg)
    raw = {r["story_id"]: r for r in _read(out / HN_RAW, RAW_SCHEMA)}
    done = _read(out / HN_WINDOWS, WINDOW_SCHEMA)
    done_keys = {(w["start_ts"], w["end_ts"]) for w in done}
    a = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
    b = int(end.replace(tzinfo=UTC).timestamp())
    size = cfg.enrich.hn_initial_window_days * 86400
    cut = int(refetch_from.replace(tzinfo=UTC).timestamp()) if refetch_from else None
    fetched = skipped = 0
    now = datetime.now(UTC).replace(tzinfo=None)

    def sink(w: Window, body: dict[str, Any]) -> None:
        nonlocal fetched
        for r in raw_rows(body, now):
            raw[r["story_id"]] = r
        done.append(
            {
                "start_ts": w.start,
                "end_ts": w.end,
                "n_hits": int(body.get("nbHits", 0)),
                "fetched_at": now,
            }
        )
        done_keys.add((w.start, w.end))
        fetched += 1
        if fetched % checkpoint_every == 0:
            _write(out / HN_RAW, list(raw.values()), RAW_SCHEMA)
            _write(out / HN_WINDOWS, done, WINDOW_SCHEMA)
            log.info("hn: %d windows fetched, %d stories", fetched, len(raw))

    for w in plan_windows(a, b, size):
        # a window is complete if it, or its halves (adaptive split), were fetched
        covered = _covered(done_keys, w)
        if covered and (cut is None or w.end <= cut):
            skipped += 1
            continue
        if covered:  # drop stale window records so they are re-fetched
            done[:] = [d for d in done if not (w.start <= d["start_ts"] and d["end_ts"] <= w.end)]
            done_keys.difference_update({k for k in done_keys if w.start <= k[0] and k[1] <= w.end})
        fetch_adaptive(hn, w, sink)
    _write(out / HN_RAW, list(raw.values()), RAW_SCHEMA)
    _write(out / HN_WINDOWS, done, WINDOW_SCHEMA)
    return {"fetched_windows": fetched, "skipped_windows": skipped, "stories_raw": len(raw)}


def _covered(done_keys: set[tuple[int, int]], w: Window) -> bool:
    """True when ``[w.start, w.end)`` is exactly tiled by completed windows."""
    if (w.start, w.end) in done_keys:
        return True
    inner = sorted(k for k in done_keys if w.start <= k[0] and k[1] <= w.end)
    pos = w.start
    for s, e in inner:
        if s != pos:
            return False
        pos = e
    return pos == w.end and bool(inner)


def build_stories(cfg: Config) -> dict[str, Any]:
    """Resolve repo names/ids as of story time and write ``hn_stories.parquet``."""
    out = enrich_dir(cfg)
    raw_path = out / HN_RAW
    hist = names_mod.history_path(cfg)
    if not raw_path.exists():
        raise FileNotFoundError("hn_raw.parquet missing; run hn-history first")
    t = pq.read_table(raw_path)
    rows = t.to_pylist()
    for r in rows:
        r["repo_name"] = parse_github_repo_url(r["url"])
    parsed = pa.Table.from_pylist(rows, schema=pa.schema([*RAW_SCHEMA, ("repo_name", pa.string())]))
    con = connect_limited()
    try:
        con.register("parsed_arrow", parsed)
        con.execute("CREATE TABLE parsed AS SELECT * FROM parsed_arrow")
        con.execute(
            """CREATE TABLE names AS SELECT DISTINCT repo_name AS name,
                      CAST(created_at AS DATE) AS as_of
               FROM parsed WHERE repo_name IS NOT NULL"""
        )
        names_mod.resolve_repo_ids(con, "names", hist).create("resolved")
        dest = out / HN_STORIES
        tmp = dest.with_suffix(".tmp")
        con.execute(
            f"""COPY (
                  SELECT p.story_id, p.created_at, p.points, p.num_comments, p.title, p.url,
                         p.repo_name, r.repo_id::BIGINT AS repo_id, p.fetched_at
                  FROM parsed p LEFT JOIN resolved r
                    ON r.name = p.repo_name AND r.as_of = CAST(p.created_at AS DATE)
                  ORDER BY p.created_at, p.story_id
                ) TO {sql_str(tmp)} (FORMAT PARQUET, COMPRESSION ZSTD)"""
        )
        tmp.replace(dest)
        by_year = con.execute(
            f"""SELECT year(created_at) y, count(*) n, count(repo_name) parsed,
                       count(repo_id) resolved
                FROM read_parquet({sql_str(dest)}) GROUP BY 1 ORDER BY 1"""
        ).fetchall()
    finally:
        con.close()
    return {"by_year": by_year, "stories": sum(r[1] for r in by_year)}


def recent_start(days: int) -> datetime:
    return (datetime.now(UTC) - timedelta(days=days)).replace(tzinfo=None)
