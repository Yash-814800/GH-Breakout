"""GitHub repository metadata for candidate-like repos (phase 4.2, ADR-017).

Target set -> GraphQL ``nodes(ids: [...])`` batches of 100 keyed on the *immutable* repo_id (the
legacy global node id ``base64("010:Repository<id>")``; ADR-017 explains the deviation from the
phase file's name lookups) -> verify ``databaseId == repo_id`` (REST ``/repositories/{id}`` on
mismatch). A null node means deleted/private/blocked and is stored as ``status='not_found'``:
such rows are kept (dropping them would add survivorship bias). Nothing fetched here that changes
over time (stargazers, description, topics, archived flag) may become a model feature; see
``config/feature_dictionary.yaml``.
"""

from __future__ import annotations

import base64
import json
import threading
from collections import deque
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from breakout.config import Config
from breakout.enrich import names as names_mod
from breakout.enrich.common import (
    atomic_copy_parquet,
    connect_limited,
    enrich_dir,
    sql_file_list,
    sql_str,
    staging_dir,
)
from breakout.enrich.http import GitHubApi
from breakout.lake import layout
from breakout.logging import get_logger

log = get_logger(__name__)

METADATA = "repo_metadata.parquet"
TARGETS = "repo_targets.parquet"
N_BUCKETS = 32

SCHEMA = pa.schema(
    [
        ("repo_id", pa.int64()),
        ("status", pa.string()),  # ok | not_found | blocked | error
        ("source", pa.string()),  # graphql | rest
        ("fetched_at", pa.timestamp("us")),
        ("name_with_owner", pa.string()),
        ("created_at", pa.timestamp("us")),
        ("is_fork", pa.bool_()),
        ("parent_repo_id", pa.int64()),
        ("is_archived", pa.bool_()),
        ("is_mirror", pa.bool_()),
        ("is_template", pa.bool_()),
        ("primary_language", pa.string()),
        ("license_spdx", pa.string()),
        ("owner_type", pa.string()),
        ("owner_login", pa.string()),
        ("owner_id", pa.int64()),
        ("owner_created_at", pa.timestamp("us")),
        ("description", pa.string()),
        ("homepage_url", pa.string()),
        ("topics", pa.list_(pa.string())),
        ("stargazer_count_at_fetch", pa.int64()),  # display only, never a feature
    ]
)

FIELDS = """
  databaseId nameWithOwner createdAt isFork parent { databaseId }
  isArchived isMirror isTemplate primaryLanguage { name } licenseInfo { spdxId }
  owner { __typename login
          ... on User { databaseId createdAt }
          ... on Organization { databaseId createdAt } }
  description homepageUrl
  repositoryTopics(first: 10) { nodes { topic { name } } }
  stargazerCount
"""


# ---- target set --------------------------------------------------------------------------------


def build_targets(cfg: Config) -> dict[str, int]:
    """Repos with >= ``candidates.min_stars_14d`` stars in a ``target_window_days`` window that
    starts within ``target_first_seen_days`` of their first observed star, using trusted-era
    WatchEvents only (``created_at < trusted_end + 1 day``). Writes ``repo_targets.parquet``
    ``(repo_id, first_star_day, max_stars_window, window_start)``.

    Memory-bounded: monthly daily-count files, then ``N_BUCKETS`` repo_id buckets.
    """
    stage = staging_dir(cfg, "targets")
    end = cfg.history.trusted_end
    files = layout.glob_for("WatchEvent", None, end, cfg)
    if not files:
        raise FileNotFoundError("no WatchEvent files in the local lake")
    by_month: dict[str, list[Path]] = {}
    for f in files:
        by_month.setdefault(names_mod._month_of(f), []).append(f)
    daily: list[Path] = []
    for month, mfiles in sorted(by_month.items()):
        out = stage / f"daily-{month}-{names_mod._signature(mfiles)}.parquet"
        daily.append(out)
        if out.exists():
            continue
        for stale in stage.glob(f"daily-{month}-*.parquet"):
            stale.unlink()
        con = connect_limited(stage / "tmp")
        try:
            atomic_copy_parquet(
                con,
                f"""SELECT repo_id, CAST(created_at AS DATE) AS day, count(*)::INTEGER AS n
                    FROM read_parquet({sql_file_list(mfiles)}, hive_partitioning=false)
                    WHERE created_at < TIMESTAMP '{(end + timedelta(days=1)).isoformat()}'
                    GROUP BY 1, 2""",
                out,
            )
        finally:
            con.close()
        log.info("targets: daily counts %s", month)
    span = cfg.enrich.target_window_days - 1
    # a month file can hold days of the neighbour month only at the edges; re-aggregate per bucket
    parts: list[Path] = []
    for b in range(N_BUCKETS):
        out = stage / f"bucket-{b:02d}-{len(daily)}-{names_mod._signature(daily)}.parquet"
        parts.append(out)
        if out.exists():
            continue
        for stale in stage.glob(f"bucket-{b:02d}-*.parquet"):
            stale.unlink()
        con = connect_limited(stage / "tmp")
        try:
            atomic_copy_parquet(
                con,
                f"""
                WITH d AS (
                  SELECT repo_id, day, sum(n)::INTEGER AS n
                  FROM read_parquet({sql_file_list(daily)})
                  WHERE repo_id % {N_BUCKETS} = {b}
                  GROUP BY 1, 2
                ), f AS (
                  SELECT *, min(day) OVER (PARTITION BY repo_id) AS first_day,
                         sum(n) OVER (PARTITION BY repo_id ORDER BY day
                                      RANGE BETWEEN CURRENT ROW AND
                                      INTERVAL {span} DAY FOLLOWING) AS w
                  FROM d
                )
                SELECT repo_id, first_day AS first_star_day,
                       max(w)::INTEGER AS max_stars_window,
                       arg_max(day, w) AS window_start
                FROM f
                WHERE day <= first_day + INTERVAL {cfg.enrich.target_first_seen_days} DAY
                  AND w >= {cfg.candidates.min_stars_14d}
                GROUP BY repo_id, first_day""",
                out,
            )
        finally:
            con.close()
        log.info("targets: bucket %d/%d", b + 1, N_BUCKETS)
    con = connect_limited(stage / "tmp")
    try:
        n = atomic_copy_parquet(
            con,
            f"SELECT * FROM read_parquet({sql_file_list(parts)})",
            enrich_dir(cfg) / TARGETS,
            order_by="repo_id",
        )
    finally:
        con.close()
    return {"targets": n, "months": len(by_month)}


# ---- parsing -----------------------------------------------------------------------------------


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).replace(tzinfo=None)


def _row(repo_id: int, status: str, source: str, fetched_at: datetime) -> dict[str, Any]:
    row: dict[str, Any] = dict.fromkeys(SCHEMA.names)
    row.update(repo_id=repo_id, status=status, source=source, fetched_at=fetched_at)
    return row


def parse_graphql_repo(repo_id: int, node: dict[str, Any], fetched_at: datetime) -> dict[str, Any]:
    """Row from a GraphQL ``repository`` node (caller has verified ``databaseId``)."""
    owner = node.get("owner") or {}
    lang = node.get("primaryLanguage") or {}
    lic = node.get("licenseInfo") or {}
    parent = node.get("parent") or {}
    topics = [
        n["topic"]["name"]
        for n in ((node.get("repositoryTopics") or {}).get("nodes") or [])
        if n and n.get("topic")
    ]
    row = _row(repo_id, "ok", "graphql", fetched_at)
    row.update(
        name_with_owner=node.get("nameWithOwner"),
        created_at=_ts(node.get("createdAt")),
        is_fork=node.get("isFork"),
        parent_repo_id=parent.get("databaseId"),
        is_archived=node.get("isArchived"),
        is_mirror=node.get("isMirror"),
        is_template=node.get("isTemplate"),
        primary_language=lang.get("name"),
        license_spdx=lic.get("spdxId"),
        owner_type=owner.get("__typename"),
        owner_login=owner.get("login"),
        owner_id=owner.get("databaseId"),
        owner_created_at=_ts(owner.get("createdAt")),
        description=node.get("description"),
        homepage_url=node.get("homepageUrl"),
        topics=topics,
        stargazer_count_at_fetch=node.get("stargazerCount"),
    )
    return row


def parse_rest_repo(repo_id: int, body: dict[str, Any], fetched_at: datetime) -> dict[str, Any]:
    owner = body.get("owner") or {}
    parent = body.get("parent") or {}
    row = _row(repo_id, "ok", "rest", fetched_at)
    row.update(
        name_with_owner=body.get("full_name"),
        created_at=_ts(body.get("created_at")),
        is_fork=body.get("fork"),
        parent_repo_id=parent.get("id"),
        is_archived=body.get("archived"),
        is_mirror=body.get("mirror_url") is not None,
        is_template=body.get("is_template"),
        primary_language=body.get("language"),
        license_spdx=(body.get("license") or {}).get("spdx_id"),
        owner_type=owner.get("type"),
        owner_login=owner.get("login"),
        owner_id=owner.get("id"),
        owner_created_at=None,  # not in the REST repository payload
        description=body.get("description"),
        homepage_url=body.get("homepage"),
        topics=list(body.get("topics") or []),
        stargazer_count_at_fetch=body.get("stargazers_count"),
    )
    return row


def node_id(repo_id: int) -> str:
    """Legacy global node id of a repository (``010:Repository<databaseId>``, base64)."""
    return base64.b64encode(f"010:Repository{repo_id}".encode()).decode()


QUERY = (
    "query($ids:[ID!]!) { rateLimit { remaining resetAt cost } "
    "nodes(ids:$ids) { __typename ... on Repository { " + FIELDS + " } } }"
)


@dataclass
class FetchStats:
    requested: int = 0
    ok: int = 0
    not_found: int = 0
    blocked: int = 0
    error: int = 0
    rest_fallbacks: int = 0
    id_mismatch: int = 0
    skipped_fresh: int = 0

    def as_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


def fetch_batch(
    api: GitHubApi,
    repo_ids: Sequence[int],
    stats: FetchStats,
    now: Callable[[], datetime] = lambda: datetime.now(UTC).replace(tzinfo=None),
) -> list[dict[str, Any]]:
    """Fetch up to 100 repos by id. Null nodes become ``not_found``; a node whose ``databaseId``
    differs from the requested id (never observed) is re-checked through REST."""
    body = api.graphql(QUERY, {"ids": [node_id(i) for i in repo_ids]})
    data = body.get("data") or {}
    nodes = data.get("nodes")
    if nodes is None or len(nodes) != len(repo_ids):
        raise RuntimeError(f"GraphQL batch failed: {str(body.get('errors'))[:300]}")
    ts = now()
    out: list[dict[str, Any]] = []
    for rid, node in zip(repo_ids, nodes, strict=True):
        if node is None:
            row = _row(rid, "not_found", "graphql", ts)
        elif node.get("databaseId") != rid:
            stats.id_mismatch += 1
            stats.rest_fallbacks += 1
            row = fetch_rest(api, rid, ts)
        else:
            row = parse_graphql_repo(rid, node, ts)
        stats.requested += 1
        setattr(stats, row["status"], getattr(stats, row["status"]) + 1)
        out.append(row)
    return out


def fetch_rest(api: GitHubApi, repo_id: int, fetched_at: datetime) -> dict[str, Any]:
    r = api.rest_get(f"/repositories/{repo_id}")
    if r.status_code == 404:
        return _row(repo_id, "not_found", "rest", fetched_at)
    if r.status_code in (403, 451):  # DMCA / disabled / blocked
        return _row(repo_id, "blocked", "rest", fetched_at)
    if r.status_code != 200:
        log.warning("REST repo %s -> HTTP %s", repo_id, r.status_code)
        return _row(repo_id, "error", "rest", fetched_at)
    body = r.json()
    if body.get("id") != repo_id:
        return _row(repo_id, "error", "rest", fetched_at)
    return parse_rest_repo(repo_id, body, fetched_at)


# ---- storage -----------------------------------------------------------------------------------


def _shard_dir(cfg: Config) -> Path:
    return enrich_dir(cfg) / ".meta_shards"


def write_shard(cfg: Config, rows: list[dict[str, Any]], seq: int) -> Path:
    d = _shard_dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    p = d / f"shard-{stamp}-{seq:05d}.parquet"
    tmp = p.with_suffix(".tmp")
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), tmp, compression="zstd")
    tmp.replace(p)
    return p


def consolidate(cfg: Config) -> int:
    """Merge the main file and shards keeping the newest ``fetched_at`` per repo_id."""
    main = enrich_dir(cfg) / METADATA
    srcs = sorted(_shard_dir(cfg).glob("shard-*.parquet"))
    if main.exists():
        srcs.insert(0, main)
    if not srcs:
        return 0
    con = connect_limited(staging_dir(cfg, "meta") / "tmp")
    cols = ", ".join(SCHEMA.names)
    try:
        n = atomic_copy_parquet(
            con,
            f"""SELECT {cols} FROM (
                  SELECT *, row_number() OVER (PARTITION BY repo_id ORDER BY fetched_at DESC) rn
                  FROM read_parquet({sql_file_list(srcs)}, union_by_name=true)
                ) WHERE rn = 1""",
            main.with_name(main.name + ".new"),
            order_by="repo_id",
        )
    finally:
        con.close()
    Path(str(main) + ".new").replace(main)
    for s in srcs:
        if s != main:
            s.unlink()
    return n


def fresh_ids(cfg: Config, max_age_days: int) -> set[int]:
    """repo_ids fetched within ``max_age_days`` (main file + unconsolidated shards)."""
    srcs = list(_shard_dir(cfg).glob("shard-*.parquet"))
    main = enrich_dir(cfg) / METADATA
    if main.exists():
        srcs.append(main)
    if not srcs:
        return set()
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=max_age_days)
    con = connect_limited()
    try:
        got = con.execute(
            f"SELECT DISTINCT repo_id FROM read_parquet({sql_file_list(srcs)}, union_by_name=true) "
            "WHERE fetched_at >= ? AND status <> 'error'",
            [cutoff],
        ).fetchall()
    finally:
        con.close()
    return {r[0] for r in got}


def load_targets(cfg: Config, ids_file: Path | None) -> list[int]:
    if ids_file is not None:
        return sorted({int(x) for x in ids_file.read_text().split() if x.strip()})
    path = enrich_dir(cfg) / TARGETS
    if not path.exists():
        build_targets(cfg)
    con = connect_limited()
    try:
        # newest repos first: recent cohorts matter most to the live model and decay fastest
        rows = con.execute(
            f"SELECT repo_id FROM read_parquet({sql_str(path)}) "
            "ORDER BY first_star_day DESC, repo_id"
        ).fetchall()
    finally:
        con.close()
    return [r[0] for r in rows]


def run_fetch(
    cfg: Config,
    api: GitHubApi,
    *,
    repo_ids_file: Path | None = None,
    limit: int | None = None,
    max_age_days: int | None = None,
    shard_every: int = 40,
    should_stop: Callable[[], bool] = lambda: False,
) -> FetchStats:
    """Fetch metadata for the target set minus fresh rows; shards every ``shard_every`` batches."""
    max_age = cfg.enrich.meta_max_age_days if max_age_days is None else max_age_days
    stats = FetchStats()
    targets = load_targets(cfg, repo_ids_file)
    fresh = fresh_ids(cfg, max_age)
    todo = [i for i in targets if i not in fresh]
    stats.skipped_fresh = len(targets) - len(todo)
    if limit is not None:
        todo = todo[:limit]
    log.info(
        "metadata: %d targets, %d fresh, %d to fetch", len(targets), stats.skipped_fresh, len(todo)
    )
    bs = cfg.enrich.graphql_batch_size
    buf: list[dict[str, Any]] = []
    seq = 0
    batches = [todo[j : j + bs] for j in range(0, len(todo), bs)]
    workers = max(1, cfg.enrich.workers)
    lock = threading.Lock()

    def work(batch: list[int]) -> list[dict[str, Any]]:
        if should_stop():
            return []
        local = FetchStats()
        rows = fetch_batch(api, batch, local)
        with lock:
            for k, v in local.as_dict().items():
                setattr(stats, k, getattr(stats, k) + v)
        return rows

    # bounded in-flight window: a stop request loses at most `workers` batches
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending: deque[Any] = deque()
        it = iter(batches)
        exhausted = False
        while pending or not exhausted:
            while not exhausted and len(pending) < workers * 2 and not should_stop():
                nxt = next(it, None)
                if nxt is None:
                    exhausted = True
                else:
                    pending.append(pool.submit(work, nxt))
            if should_stop():
                exhausted = True
            if not pending:
                break
            buf.extend(pending.popleft().result())
            if len(buf) >= shard_every * bs:
                seq += 1
                write_shard(cfg, buf, seq)
                buf = []
                log.info("metadata: %s", json.dumps(stats.as_dict()))
    if buf:
        seq += 1
        write_shard(cfg, buf, seq)
    n = consolidate(cfg)
    log.info("metadata: consolidated %d rows; %s", n, json.dumps(stats.as_dict()))
    return stats
