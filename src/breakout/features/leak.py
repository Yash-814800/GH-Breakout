"""Time-travel leak test for ``mart_repo_features`` (Phase 7, 7.2.1).

For a snapshot date D and a sample of its candidates, the feature SQL runs twice on small copies of the
warehouse tables it reads:

  full       every row of the sampled repos, including rows at or after D
  truncated  the same, with every input cut at D (``time < D``): what the world looked like at D

Both runs use the real dbt models (``snapshot_dates_mode = single``, ``events_end = D``). Every feature of
every sampled ``(repo_id, D)`` must be identical (floats within 1e-9); any difference means a model read a
row that was not known before D. The truncated copy cannot be rebuilt from raw events (that is the full
history build), so it cuts the materialised inputs at their own timestamp columns:

  * tables keyed by a time column (star day, event time, action time, opened_at, ...) keep rows ``< D``;
  * outcome timestamps of issues and PRs (first response, close, merge, review) that fall at or after D
    become NULL: the thing had not happened yet;
  * a contributor session that straddles D ends one second before D (its true end is only known later; a
    complete session needs ``session_end + gap < D``, so it must not be used);
  * ``int_actor_early_stars`` is copied for the sampled stargazers (all their early stars on any repo) and for
    the hit repos of the sampled owners; in the truncated copy rows from D on are removed and the hit flag of a
    star whose 60-day outcome is not yet known at D (``outcome_day >= D``) is cleared. ``int_actor_early_cum``
    and ``int_repo_first_hit`` are REBUILT from it with the same SQL; the month thresholds, which need every
    actor, are copied (they only depend on outcomes known before D).

Derived columns of the materialised intermediates (e.g. ``actor_events_prior_90d``) are leak-free by their own
construction (Phase 5 tests); this test covers the Phase 7 SQL.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from breakout import dbt_runner
from breakout import paths as P
from breakout.config import Config
from breakout.logging import get_logger

log = get_logger(__name__)

# int_actor_early_stars is COPIED (rows of the sampled stargazers and of the owners' hit repos), not rebuilt:
# rebuilding it needs every early star of every repo a bulk starrer ever touched (millions of rows)
FEATURE_MODELS = [
    "int_actor_early_cum",
    "int_repo_first_hit",
    "feat_star_dynamics",
    "feat_activity",
    "feat_stargazers",
    "feat_tastemaker",
    "feat_owner",
    "feat_detail",
    "feat_enrich",
    "mart_repo_features",
]
KEY = ("repo_id", "snapshot_date")
FLOAT_TOL = 1e-9


@dataclass
class LeakResult:
    snapshot_date: date
    sample: int
    rows_compared: int = 0
    columns_compared: int = 0
    differences: list[dict[str, Any]] = field(default_factory=list)
    history_rows_compared: int = 0
    history_differences: int = 0
    informative_columns: int = (
        0  # columns with at least one non-NULL value (a test of all-NULL columns proves nothing)
    )

    @property
    def passed(self) -> bool:
        return not self.differences

    def summary(self) -> str:
        hist = (
            f"; vs history mart: {self.history_rows_compared} rows, {self.history_differences} differing"
            if self.history_rows_compared
            else ""
        )
        status = "PASS" if self.passed else f"FAIL ({len(self.differences)} differing columns)"
        return (
            f"leak-test {self.snapshot_date}: {status}: {self.rows_compared} rows x "
            f"{self.columns_compared} columns compared (full vs truncated at D; "
            f"{self.informative_columns} have non-NULL values){hist}"
        )


def _q(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple]:
    return con.execute(sql).fetchall()


def sample_candidates(src: duckdb.DuckDBPyConnection, d: date, n: int, seed: int = 42) -> list[int]:
    """Deterministic sample of the candidates of snapshot ``d`` (hash order, not RNG state)."""
    rows = _q(
        src,
        f"""select repo_id from src.mart_candidates where snapshot_date = date '{d}'
            order by hash(repo_id + {seed}), repo_id limit {int(n)}""",
    )
    return [r[0] for r in rows]


def _owner_closure(src: duckdb.DuckDBPyConnection, repo_ids: str, d: date) -> list[int]:
    """Repos that ever carried a name with the same owner prefix as a sampled repo (feat_owner)."""
    rows = _q(
        src,
        f"""with o as (
                select distinct lower(split_part(repo_name_at_D, '/', 1)) as owner
                from src.mart_candidates
                where snapshot_date = date '{d}' and repo_id in ({repo_ids}))
            select distinct repo_id from src.stg_repo_name_history
            where lower(split_part(repo_name, '/', 1)) in (select owner from o)""",
    )
    return [r[0] for r in rows]


def _make_copy(
    mini: Path, src_path: Path, d: date, sample: list[int], truncate: bool
) -> dict[str, int]:
    """Create the small warehouse ``mini`` (see module docstring). Returns row counts per table."""
    if mini.exists():
        mini.unlink()
    con = duckdb.connect(str(mini))
    con.execute("SET memory_limit='1500MB'")
    con.execute("SET threads=1")
    con.execute(f"SET temp_directory='{(P.TMP_DIR / 'leak').as_posix()}'")
    con.execute(f"ATTACH '{src_path}' AS src (READ_ONLY)")
    con.execute("create table sample_repos as select unnest(?)::bigint as repo_id", [sample])
    ids = ",".join(str(i) for i in sample)
    day = f"date '{d}'"
    ts = f"timestamp '{d} 00:00:00'"

    def cut(col: str, kind: str = "ts") -> str:
        if not truncate:
            return "true"
        return f"{col} < {ts if kind == 'ts' else day}"

    owner_repos = _owner_closure(con, ids, d)
    con.execute("create table owner_repos as select unnest(?)::bigint as repo_id", [owner_repos])
    # actors who starred a sampled repo (before D in the truncated copy): their early stars drive the tastemaker
    con.execute(
        f"""create table stargazers as
            select distinct actor_id from src.int_early_stars
            where repo_id in (select repo_id from sample_repos) and {cut("starred_at")}"""
    )
    counts: dict[str, int] = {}

    def make(name: str, sql: str) -> None:
        con.execute(f"create table {name} as {sql}")
        counts[name] = con.execute(f"select count(*) from {name}").fetchone()[0]  # type: ignore[index]

    sample_f = "repo_id in (select repo_id from sample_repos)"
    make(
        "mart_candidates",
        f"select * from src.mart_candidates where snapshot_date = {day} and {sample_f}",
    )
    make(
        "int_repo_star_daily",
        f"select * from src.int_repo_star_daily where {sample_f} and {cut('day', 'date')}",
    )
    make("int_repo_birth", f"select * from src.int_repo_birth where {sample_f}")
    make(
        "int_early_stars",
        f"select * from src.int_early_stars where {sample_f} and {cut('starred_at')}",
    )
    unknown = (
        f"* replace (case when outcome_day >= {day} then false else is_hit end as is_hit, "
        f"case when outcome_day >= {day} then null else gain_lookahead end as gain_lookahead)"
        if truncate
        else "*"
    )
    make(
        "int_actor_early_stars",
        f"""select {unknown} from src.int_actor_early_stars
            where (actor_id in (select actor_id from stargazers)
                   or (repo_id in (select repo_id from owner_repos) and is_hit))
              and {cut("star_day", "date")}""",
    )
    make(
        "int_star_events_enriched",
        f"select * from src.int_star_events_enriched where {sample_f} and {cut('starred_at')}",
    )
    make(
        "int_stargazer_later_actions",
        f"select * from src.int_stargazer_later_actions where {sample_f} and {cut('action_at')}",
    )
    make(
        "int_repo_daily_activity",
        f"select * from src.int_repo_daily_activity where {sample_f} and {cut('day', 'date')}",
    )
    make(
        "int_core_actors_daily",
        f"select * from src.int_core_actors_daily where {sample_f} and {cut('day', 'date')}",
    )
    straddle = (
        f"* replace (case when session_end >= {ts} then {ts} - interval 1 second else session_end end "
        "as session_end)"
        if truncate
        else "*"
    )
    make(
        "int_contributor_sessions",
        f"select {straddle} from src.int_contributor_sessions where {sample_f} and {cut('session_start')}",
    )
    if truncate:
        null_late = lambda c: f"case when {c} >= {ts} then null else {c} end as {c}"  # noqa: E731
        issue_sel = f"* replace ({null_late('first_response_at')}, {null_late('closed_at')})"
        pr_sel = (
            f"* replace ({null_late('closed_at')}, {null_late('merged_at')}, "
            f"{null_late('first_review_at')})"
        )
    else:
        issue_sel = pr_sel = "*"
    make(
        "int_issue_response",
        f"select {issue_sel} from src.int_issue_response where {sample_f} and {cut('opened_at')}",
    )
    make(
        "int_pr_lifecycle",
        f"select {pr_sel} from src.int_pr_lifecycle where {sample_f} and {cut('opened_at')}",
    )
    make(
        "stg_stars",
        f"select * from src.stg_stars where {sample_f} and {cut('starred_at')}",
    )
    owner_names = "select distinct lower(split_part(repo_name_at_D, '/', 1)) from mart_candidates"
    name_sel = f"* replace (least(last_seen, {ts}) as last_seen)" if truncate else "*"
    make(
        "stg_repo_name_history",
        f"""select {name_sel} from src.stg_repo_name_history
            where lower(split_part(repo_name, '/', 1)) in ({owner_names}) and {cut("first_seen")}""",
    )
    make("stg_repo_metadata", f"select * from src.stg_repo_metadata where {sample_f}")
    make(
        "stg_hn_stories",
        f"select * from src.stg_hn_stories where {sample_f} and {cut('created_at')}",
    )
    make(
        "int_tastemaker_thresholds",
        f"select * from src.int_tastemaker_thresholds where month <= {day}",
    )
    make("top_languages", "select * from src.top_languages")
    con.execute("DETACH src")
    con.close()
    return counts


def _run_dbt(cfg: Config, mini: Path, d: date) -> None:
    prev = {k: os.environ.get(k) for k in ("GHB_WAREHOUSE", "GHB_DUCKDB_MEMORY")}
    os.environ["GHB_WAREHOUSE"] = str(mini)
    os.environ["GHB_DUCKDB_MEMORY"] = "1500MB"
    try:
        rc = dbt_runner.run_dbt(
            cfg,
            ["run", "--select", *FEATURE_MODELS, "--full-refresh"],
            extra_vars={
                "snapshot_dates_mode": "single",
                "snapshot_date": d.isoformat(),
                "events_end": d.isoformat(),
                "n_buckets": 1,
            },
        )
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    if rc != 0:
        raise RuntimeError(f"dbt run failed in {mini} (exit {rc})")


def _neq(c: str, dtype: str, tol: float) -> str:
    """SQL: column ``c`` differs between x and y (NULLs equal, floats within ``tol``)."""
    if dtype in ("DOUBLE", "FLOAT") or dtype.startswith("DECIMAL"):
        return (
            f"(x.{c} is distinct from y.{c} and not (x.{c} is not null and y.{c} is not null "
            f"and abs(x.{c} - y.{c}) <= {tol}))"
        )
    return f"x.{c} is distinct from y.{c}"


def compare_features(
    full: Path, trunc: Path, tol: float = FLOAT_TOL, table: str = "mart_repo_features"
) -> tuple[int, int, list[dict[str, Any]]]:
    """Compare two feature marts column by column. Returns (rows, columns, differences)."""
    con = duckdb.connect()
    con.execute(f"ATTACH '{full}' AS a (READ_ONLY)")
    con.execute(f"ATTACH '{trunc}' AS b (READ_ONLY)")
    cols_a = [
        r[0]
        for r in _q(
            con,
            f"select column_name from information_schema.columns where table_catalog='a' and table_name='{table}' order by ordinal_position",
        )
    ]
    cols_b = [
        r[0]
        for r in _q(
            con,
            f"select column_name from information_schema.columns where table_catalog='b' and table_name='{table}' order by ordinal_position",
        )
    ]
    if cols_a != cols_b:
        raise RuntimeError(f"column lists differ: {set(cols_a) ^ set(cols_b)}")
    types = dict(
        _q(
            con,
            f"select column_name, data_type from information_schema.columns where table_catalog='a' and table_name='{table}'",
        )
    )
    n_a = _q(con, f"select count(*) from a.main.{table}")[0][0]
    n_both = _q(
        con,
        f"select count(*) from a.main.{table} x join b.main.{table} y using (repo_id, snapshot_date)",
    )[0][0]
    diffs: list[dict[str, Any]] = []
    if n_a != n_both:
        diffs.append(
            {"column": "<rows>", "n_diff": abs(n_a - n_both), "example": f"{n_a} vs {n_both}"}
        )
    feature_cols = [c for c in cols_a if c not in (*KEY, "bucket")]
    for c in feature_cols:
        neq = _neq(c, types[c], tol)
        rows = _q(
            con,
            f"""select count(*), min(x.repo_id), any_value(x.{c}::varchar), any_value(y.{c}::varchar)
                from a.main.{table} x join b.main.{table} y using (repo_id, snapshot_date) where {neq}""",
        )[0]
        if rows[0]:
            diffs.append(
                {
                    "column": c,
                    "n_diff": rows[0],
                    "example": f"repo_id {rows[1]}: full={rows[2]} truncated={rows[3]}",
                }
            )
    con.close()
    return n_both, len(feature_cols), diffs


def informative_columns(path: Path, table: str = "mart_repo_features") -> int:
    """Number of feature columns with at least one non-NULL value in ``path``."""
    con = duckdb.connect(str(path), read_only=True)
    try:
        cols = [
            r[0]
            for r in _q(
                con,
                f"select column_name from information_schema.columns where table_name='{table}'",
            )
            if r[0] not in (*KEY, "bucket")
        ]
        agg = ", ".join(f"count({c}) > 0" for c in cols)
        return int(sum(bool(v) for v in con.execute(f"select {agg} from {table}").fetchone()))  # type: ignore[union-attr]
    finally:
        con.close()


def compare_with_history(mini: Path, src_path: Path, tol: float = FLOAT_TOL) -> tuple[int, int]:
    """Rows of the full mini mart versus the same rows of the real history mart (copy fidelity check)."""
    con = duckdb.connect()
    con.execute(f"ATTACH '{mini}' AS a (READ_ONLY)")
    con.execute(f"ATTACH '{src_path}' AS h (READ_ONLY)")
    exists = _q(
        con,
        "select count(*) from information_schema.tables where table_catalog='h' and table_name='mart_repo_features'",
    )[0][0]
    if not exists:
        return 0, 0
    cols = [
        (r[0], r[1])
        for r in _q(
            con,
            "select column_name, data_type from information_schema.columns where table_catalog='a' and table_name='mart_repo_features' order by ordinal_position",
        )
        if r[0] not in (*KEY, "bucket")
    ]
    cond = " or ".join(_neq(c, t, tol) for c, t in cols)
    n = _q(
        con,
        "select count(*) from a.main.mart_repo_features x join h.main.mart_repo_features y using (repo_id, snapshot_date)",
    )[0][0]
    bad = _q(
        con,
        f"select count(*) from a.main.mart_repo_features x join h.main.mart_repo_features y using (repo_id, snapshot_date) where {cond}",
    )[0][0]
    con.close()
    return n, bad


def run_leak_test(
    cfg: Config,
    d: date,
    sample: int = 300,
    warehouse: Path | None = None,
    workdir: Path | None = None,
) -> LeakResult:
    """Run the full time-travel test for one date; raises nothing on a leak, see ``LeakResult.passed``."""
    src_path = Path(warehouse or os.environ.get("GHB_WAREHOUSE") or P.WAREHOUSE)
    # small DuckDB files are written on the local disk (the NTFS SSD stalls under DuckDB writes, ADR-020)
    workdir = workdir or (Path.home() / ".cache" / "ghb-leak")
    workdir.mkdir(parents=True, exist_ok=True)
    probe = duckdb.connect()
    probe.execute(f"ATTACH '{src_path}' AS src (READ_ONLY)")
    ids = sample_candidates(probe, d, sample)
    probe.close()
    if not ids:
        raise RuntimeError(f"no candidates on {d} in {src_path}")
    full, trunc = workdir / f"leak_full_{d}.duckdb", workdir / f"leak_trunc_{d}.duckdb"
    for path, truncate in ((full, False), (trunc, True)):
        log.info(
            "leak-test %s: copy (%s) of %d repos", d, "truncated" if truncate else "full", len(ids)
        )
        counts = _make_copy(path, src_path, d, ids, truncate)
        log.info("leak-test %s: copied %s", d, counts)
        _run_dbt(cfg, path, d)
    rows, ncols, diffs = compare_features(full, trunc)
    res = LeakResult(d, len(ids), rows, ncols, diffs)
    res.informative_columns = informative_columns(full)
    res.history_rows_compared, res.history_differences = compare_with_history(full, src_path)
    for diff in diffs:
        log.error("leak: %s", diff)
    log.info(res.summary())
    return res
