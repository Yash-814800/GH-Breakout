"""Dataset/model cards (``README.md``) rendered from templates in ``lake/cards/``.

Schema tables come from ``schema.py`` and coverage from the catalog, so the cards cannot drift
from the data. License is MIT (ADR-013) with provenance wording that claims no rights in the
underlying events.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

import pyarrow as pa

from breakout.config import Config
from breakout.lake import catalog as cat
from breakout.schema import EVENTS_SCHEMA, PUSH_DAILY_SCHEMA, SCHEMA_VERSION

CARDS_DIR = Path(__file__).parent / "cards"
PROJECT_URL = "https://github.com/Yash-814800/GH-Breakout"

DESCRIPTIONS = {
    "event_id": "GitHub event id (unique per event)",
    "event_type": "GitHub event type (also the hive partition key)",
    "created_at": "event time, naive UTC timestamp",
    "repo_id": "numeric repository id (stable across renames; use as key)",
    "repo_name": "`owner/name` at event time (display only)",
    "actor_id": "numeric id of the user or bot that acted",
    "actor_login": "login at event time (display only)",
    "org_id": "owning organization id, if any",
    "detail_level": "0 = spine columns only, 1 = payload parsed",
    "action": "payload action (Watch, Issues, IssueComment, PullRequest, Review, Release)",
    "number": "issue / pull request number",
    "is_pull_request": "comment or event is on a pull request",
    "target_user_id": "author of the pull request, when present in the payload",
    "target_created_at": "creation time of the target issue/PR, when present",
    "pr_merged": "PullRequestEvent closed with merged = true",
    "review_state": "review state (approved, changes_requested, ...)",
    "ref_type": "CreateEvent ref type (repository, branch, tag)",
    "forkee_repo_id": "id of the new fork (ForkEvent)",
    "release_prerelease": "release is a pre-release",
    "source": "`bq` (BigQuery history) or `hourly` (data.gharchive.org hourly files)",
    "ingested_at": "when this row was written, naive UTC",
    "n_pushes": "PushEvents by this actor to this repo on this day",
    "day": "UTC day",
}


def _schema_md(schema: pa.Schema) -> str:
    lines = ["| column | type | nullable | description |", "|---|---|---|---|"]
    for f in schema:
        nullable = "yes" if f.nullable else "no"
        lines.append(f"| `{f.name}` | {f.type} | {nullable} | {DESCRIPTIONS.get(f.name, '')} |")
    return "\n".join(lines)


def _size_category(rows: int) -> str:
    bounds = [
        (1_000, "n<1K"),
        (10_000, "1K<n<10K"),
        (100_000, "10K<n<100K"),
        (1_000_000, "100K<n<1M"),
        (10_000_000, "1M<n<10M"),
        (100_000_000, "10M<n<100M"),
        (1_000_000_000, "100M<n<1B"),
        (10_000_000_000, "1B<n<10B"),
        (100_000_000_000, "10B<n<100B"),
    ]
    for limit, name in bounds:
        if rows < limit:
            return name
    return "n>100B"


def coverage_md(catalog: pa.Table) -> str:
    rows = catalog.to_pylist()
    if not rows:
        return "_No files published yet._"
    out: list[str] = []
    for table in (cat.EVENTS_TABLE, cat.PUSH_TABLE):
        rs = [r for r in rows if r["table"] == table]
        if not rs:
            continue
        lo = min(r["min_created_at"] for r in rs if r["min_created_at"])
        hi = max(r["max_created_at"] for r in rs if r["max_created_at"])
        n = sum(r["rows"] for r in rs)
        gb = sum(r["bytes"] for r in rs) / 1e9
        by_src: dict[str, int] = {}
        for r in rs:
            key = f"{r['source_min']}" if r["source_min"] == r["source_max"] else "mixed"
            by_src[key] = by_src.get(key, 0) + r["rows"]
        dl = {(r["detail_level_min"], r["detail_level_max"]) for r in rs}
        out.append(
            f"- **{table}**: {lo:%Y-%m-%d} .. {hi:%Y-%m-%d}, {len(rs)} files, {n:,} rows, "
            f"{gb:.1f} GB; rows by source file: {by_src}; "
            f"detail_level ranges: {sorted(dl, key=str)}"
        )
    return "\n".join(out)


def render_events(cfg: Config, catalog: pa.Table) -> str:
    rows = catalog.to_pylist()
    ev = [r for r in rows if r["table"] == cat.EVENTS_TABLE]
    types = sorted({r["event_type"] for r in ev}) or list(cfg.events.raw_types)
    configs = [
        f"- config_name: {t}\n  data_files: events/event_type={t}/**/*.parquet" for t in types
    ]
    configs.append("- config_name: push_daily\n  data_files: push_daily/**/*.parquet")
    repo = cfg.huggingface.require_events_repo()
    return Template((CARDS_DIR / "events.md").read_text(encoding="utf-8")).substitute(
        size_category=_size_category(sum(r["rows"] for r in ev)),
        configs="\n".join(configs),
        project_url=PROJECT_URL,
        event_types=", ".join(f"`{t}`" for t in types),
        schema_version=SCHEMA_VERSION,
        events_schema=_schema_md(EVENTS_SCHEMA),
        push_schema=_schema_md(PUSH_DAILY_SCHEMA),
        coverage=coverage_md(catalog),
        repo=repo,
    )


def render_simple(cfg: Config, name: str) -> str:
    return Template((CARDS_DIR / f"{name}.md").read_text(encoding="utf-8")).substitute(
        project_url=PROJECT_URL,
        events_repo=cfg.huggingface.require_events_repo(),
    )


def render_all(cfg: Config, catalog: pa.Table) -> dict[str, str]:
    """repo key -> README.md text."""
    return {
        "events": render_events(cfg, catalog),
        "derived": render_simple(cfg, "derived"),
        "snapshots": render_simple(cfg, "snapshots"),
        "models": render_simple(cfg, "models"),
    }
