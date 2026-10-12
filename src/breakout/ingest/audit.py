"""Payload audit: which JSON paths exist per event type per era (Phase 1).

Streams a handful of sample hours line by line (never loading a whole file), measures presence
rates for every ``payload`` path up to depth 3, writes ``docs/schema_audit.md`` and saves small
fixtures for the parser tests.
"""

from __future__ import annotations

import gzip
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

from breakout.ingest.gharchive import download_hour, hour_url
from breakout.logging import get_logger

log = get_logger(__name__)

SAMPLE_DAYS = (
    "2015-03-02",
    "2016-06-01",
    "2018-06-01",
    "2020-06-01",
    "2022-06-01",
    "2024-06-03",
    "2025-09-01",
    "2025-11-03",
)
SAMPLE_HOUR = 12
TRIM_DATE = date(2025, 10, 7)
FIXTURE_CAP = 150
FIXTURE_MAX_BYTES = 1_800_000
MAX_DEPTH = 3  # path components below ``payload``
TOP_LEVEL = "_top"

PARSER_DECISIONS = """\
## Parser decisions

All paths below were verified against the sampled hours above (presence % per era, in sample
order 2015 / 2016 / 2018 / 2020 / 2022 / 2024 / 2025-09 / 2025-11 / 2026-10). "Post-trim" means
2025-11-03 and 2026-10-10. A path that is absent in an era yields NULL; nothing is imputed.
No era-specific path fallbacks were needed beyond the `COALESCE`s listed here.

| column | JSON path(s) used | availability across eras | downstream features affected |
|---|---|---|---|
| `event_id` | `id` (string of digits, `TRY_CAST` to BIGINT) | all eras; rows that fail are dropped and counted as `bad_ids` | none |
| `created_at` | `created_at` (ISO-8601 `Z`) -> naive UTC `TIMESTAMP` | all eras | all (point-in-time cut) |
| `repo_id`, `repo_name` | `repo.id`, `repo.name` | all eras. A very small number of events have `repo: {}` (seen 2026-10-10, ForkEvent); they are dropped and counted in `bad_ids` | all |
| `actor_id`, `actor_login` | `actor.id`, `actor.login` | all eras | tastemaker / stargazer features |
| `org_id` | `org.id` | present on only ~28-41% of events in every era (genuinely nullable) | owner-type proxy |
| `action` | `payload.action` for Watch / Issues / IssueComment / PullRequest / PullRequestReview / Release | 100% in every era where the type exists (PullRequestReviewEvent only from the 2022 sample on). `ForkEvent.payload.action` is 0% until 2025-11 and is deliberately not extracted | issue/PR open and close counts |
| `number` | Issues/IssueComment: `payload.issue.number`; PullRequest: `COALESCE(payload.pull_request.number, payload.number)`; Review: same | 100% wherever the type exists; `payload.number` is absent on review events, `payload.pull_request.number` covers it | issue/PR de-duplication |
| `is_pull_request` | PullRequest/Review events: TRUE; IssuesEvent: FALSE (GitHub never emits IssuesEvent for a PR; `payload.issue.pull_request` is 0% on those); IssueCommentEvent: `payload.issue.pull_request` is present and non-null | PR-comment share is 35% (2015) rising to 65-72% (2022+); stable across the trim | PR vs issue discussion features |
| `target_user_id` | `payload.issue.user.id` / `payload.pull_request.user.id` | issues/comments: 100% all eras. **PR and review events: 100% until 2025-09, 0% post-trim** | "external contributor" and maintainer-reply features lose PR authorship after 2025-10-07 |
| `target_created_at` | `payload.issue.created_at` / `payload.pull_request.created_at` | issues/comments: 100% all eras. **PR and review events: 0% post-trim** | issue/PR response-time features for PRs |
| `pr_merged` | `payload.pull_request.merged` only when `payload.action = 'closed'` (PullRequestEvent) | 100% until 2025-09, **0% post-trim** | merged-PR count features are not computable after 2025-10-07 |
| `review_state` | `payload.review.state` | 100% wherever the type exists (all eras incl. post-trim) | review activity features |
| `ref_type` | `payload.ref_type` (CreateEvent) | 100% all eras | repo birth detection (`repository`), branch/tag counts |
| `forkee_repo_id` | `payload.forkee.id` (ForkEvent) | 100% all eras | fork-graph features |
| `release_prerelease` | `payload.release.prerelease` (ReleaseEvent) | 100% all eras | release cadence features |
| `push_daily` | PushEvent: `repo.id`, `actor.id`, `created_at`, `repo.name` only (no payload field used) | all eras. `payload.commits`, `payload.size` and `payload.distinct_size` vanish post-trim and are never used | commit counts per push are NOT available; only push counts |

Fields that GitHub trimmed on 2025-10-07 and that we therefore never rely on:
`author_association` (issue / comment / PR), `pull_request.user`, `pull_request.merged`,
`pull_request.created_at`, `_links`, push `commits` / `size` / `distinct_size`.
"""

VOLUME_NOTES = """\
## Data-volume observations (manual probe, 2026-10-12)

The sample table above shows WatchEvent (stars) rows per sampled hour falling from 4,653
(2025-09-01) to 2,967 (2025-11-03) to 346 (2026-10-10), while PushEvent, CreateEvent and
PullRequestEvent stay in the same range. Extra probes of the 12:00 UTC hour (events counted
straight from the public hourly files with `grep`, not through the parser):

| day | WatchEvent | IssuesEvent | ForkEvent |
|---|---:|---:|---:|
| 2025-09-15 | 4,447 | 2,215 | 1,112 |
| 2025-10-08 | 4,532 | 2,638 | 1,165 |
| 2025-11-15 | 3,519 | 3,142 | 840 |
| 2025-12-15 | 2,297 | 2,111 | 514 |
| 2026-02-15 | 3,264 | 2,869 | 703 |
| 2026-04-15 | 872 | 1,014 | 176 |
| 2026-06-15 | 119 | 127 | 28 |
| 2026-08-15 | 24 | 31 | 5 |
| 2026-09-15 | 1,158 | 2,052 | 248 |
| 2026-10-10 | 346 | 709 | 87 |

2026-08-15 stays at roughly 17-42 WatchEvents in *every* hour of the day, so this is a property
of the archived stream, not of one bad file. Whole-archive star events are therefore far sparser
since about 2026-03 than the model's label and candidate definitions assume. This must be
resolved (or the label/candidate thresholds re-derived) before any modeling on post-2026-03 data.
"""


@dataclass
class HourAudit:
    day: str
    hour: int
    lines: int = 0
    bad_lines: int = 0
    type_counts: Counter[str] = field(default_factory=Counter)
    path_counts: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))

    def to_json(self) -> dict:
        return {
            "day": self.day,
            "hour": self.hour,
            "lines": self.lines,
            "bad_lines": self.bad_lines,
            "type_counts": dict(self.type_counts),
            "path_counts": {t: dict(c) for t, c in self.path_counts.items()},
        }

    @classmethod
    def from_json(cls, d: dict) -> HourAudit:
        a = cls(d["day"], d["hour"], d["lines"], d["bad_lines"])
        a.type_counts = Counter(d["type_counts"])
        for t, c in d["path_counts"].items():
            a.path_counts[t] = Counter(c)
        return a


def _walk(obj: dict, prefix: str, depth: int, out: set[str]) -> None:
    for key, value in obj.items():
        if value is None:
            continue
        path = f"{prefix}.{key}"
        out.add(path)
        if isinstance(value, dict) and depth < MAX_DEPTH:
            _walk(value, path, depth + 1, out)


def event_paths(event: dict) -> set[str]:
    out: set[str] = set()
    payload = event.get("payload")
    if isinstance(payload, dict):
        _walk(payload, "payload", 1, out)
    return out


def _top_paths(event: dict) -> set[str]:
    out = {k for k, v in event.items() if v is not None and k != "payload"}
    for parent in ("actor", "repo", "org"):
        sub = event.get(parent)
        if isinstance(sub, dict):
            out.update(f"{parent}.{k}" for k, v in sub.items() if v is not None)
    return out


def audit_file(
    path: Path, day: str, hour: int, types: set[str], fixture_out: Path | None = None
) -> HourAudit:
    """Stream one hourly file. ``fixture_out`` receives up to FIXTURE_CAP raw lines per type."""
    audit = HourAudit(day, hour)
    kept: dict[str, list[bytes]] = defaultdict(list)
    with gzip.open(path, "rb") as fh:
        for raw in fh:
            audit.lines += 1
            try:
                ev = json.loads(raw)
                etype = ev["type"]
            except (ValueError, KeyError, TypeError):
                audit.bad_lines += 1
                continue
            if etype not in types:
                continue
            audit.type_counts[etype] += 1
            counter = audit.path_counts[etype]
            for p in event_paths(ev):
                counter[p] += 1
            top = audit.path_counts[TOP_LEVEL]
            for p in _top_paths(ev):
                top[f"{etype}:{p}"] += 1
            if len(kept[etype]) < FIXTURE_CAP:
                kept[etype].append(raw if raw.endswith(b"\n") else raw + b"\n")
    if fixture_out is not None:
        write_fixture(kept, fixture_out)
    return audit


def write_fixture(kept: dict[str, list[bytes]], out: Path) -> None:
    """Write fixture lines, shrinking the per-type cap until the file is small enough."""
    cap = FIXTURE_CAP
    out.parent.mkdir(parents=True, exist_ok=True)
    while True:
        # mtime=0 and sorted types -> byte-identical output for identical input
        with open(out, "wb") as raw_out, gzip.GzipFile(fileobj=raw_out, mode="wb", mtime=0) as gz:
            for etype in sorted(kept):
                for line in kept[etype][:cap]:
                    gz.write(line)
        if out.stat().st_size <= FIXTURE_MAX_BYTES or cap <= 5:
            return
        cap = max(5, cap // 2)
        log.info("fixture %s too large, reducing cap to %d", out.name, cap)


def latest_complete_day(now: datetime, client: httpx.Client) -> date:
    """Latest UTC day whose hour-23 file exists, probing backward from now - 3h."""
    t = (now - timedelta(hours=3)).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    day = t.date() if t.hour == 23 else t.date() - timedelta(days=1)
    for _ in range(14):
        url = hour_url(datetime(day.year, day.month, day.day, 23))
        r = client.head(url)
        if r.status_code == 200:
            return day
        day -= timedelta(days=1)
    raise RuntimeError("no complete GH Archive day found in the last 14 days")


def _pct(n: int, total: int) -> float:
    return 100.0 * n / total if total else 0.0


def render_markdown(audits: list[HourAudit], types: list[str], generated: date) -> str:
    audits = sorted(audits, key=lambda a: a.day)
    eras = [a.day for a in audits]
    pre = [a for a in audits if date.fromisoformat(a.day) < TRIM_DATE]
    post = [a for a in audits if date.fromisoformat(a.day) >= TRIM_DATE]
    lines: list[str] = []
    w = lines.append
    w("# Payload schema audit")
    w("")
    w(f"Generated {generated} by `breakout ingest audit`. Source: one hour (12:00 UTC) of")
    w("GH Archive for each sampled day below. Presence % = share of that type's events in the")
    w("sample hour where the JSON path exists and is not null. Paths are listed to depth 3")
    w("below `payload`. A `—` means the type had zero events in that sample hour.")
    w("**Samples are one hour each; small types (PublicEvent, ReleaseEvent) can have very few")
    w("rows, check the count row.**")
    w("")
    w("Legend: ⚠ = presence ≥ 50% before 2025-10-07 and < 50% after (GitHub payload trimming).")
    w("")
    w("## Sampled hours")
    w("")
    w("| day (12:00 UTC) | lines | bad lines | " + " | ".join(types) + " |")
    w("|---|---:|---:|" + "---:|" * len(types))
    for a in audits:
        w(
            f"| {a.day} | {a.lines:,} | {a.bad_lines} | "
            + " | ".join(f"{a.type_counts.get(t, 0):,}" for t in types)
            + " |"
        )
    w("")
    drops: dict[str, list[str]] = {}
    sections: list[str] = []
    for t in types:
        paths: set[str] = set()
        for a in audits:
            paths.update(a.path_counts.get(t, {}))
        sec: list[str] = []
        sec.append(f"## {t}")
        sec.append("")
        sec.append("| path | " + " | ".join(eras) + " |")
        sec.append("|---|" + "---:|" * len(eras))
        sec.append(
            "| *(rows in sample)* | "
            + " | ".join(f"{a.type_counts.get(t, 0):,}" for a in audits)
            + " |"
        )
        flagged: list[str] = []
        for p in sorted(paths):
            cells = []
            vals: dict[str, float | None] = {}
            for a in audits:
                n = a.type_counts.get(t, 0)
                if n == 0:
                    cells.append("—")
                    vals[a.day] = None
                else:
                    v = _pct(a.path_counts[t].get(p, 0), n)
                    vals[a.day] = v
                    cells.append(f"{v:.0f}" if v >= 1 or v == 0 else "<1")
            pre_v = [x for a in pre if (x := vals[a.day]) is not None]
            post_v = [x for a in post if (x := vals[a.day]) is not None]
            mark = ""
            if pre_v and post_v and max(pre_v[-2:]) >= 50 and max(post_v) < 50:
                mark = " ⚠"
                flagged.append(p)
            sec.append(f"| `{p}`{mark} | " + " | ".join(cells) + " |")
        drops[t] = flagged
        sections.append("\n".join(sec))
        sections.append("")
    w("## Fields dropping below 50% after 2025-10-07")
    w("")
    any_drop = False
    for t in types:
        if drops[t]:
            any_drop = True
            w(f"- **{t}**: " + ", ".join(f"`{p}`" for p in drops[t]))
    if not any_drop:
        w("_None detected in the sampled hours._")
    w("")
    w(VOLUME_NOTES)
    w(PARSER_DECISIONS)
    lines.extend(sections)
    return "\n".join(lines)


def run_audit(
    types: list[str],
    *,
    raw_dir: Path,
    cache_dir: Path,
    fixture_dir: Path,
    docs_path: Path,
    now: datetime | None = None,
    keep_raw: bool = False,
) -> Path:
    """Download the sample hours, audit them, write fixtures and the markdown report."""
    now = now or datetime.now(UTC)
    cache_dir.mkdir(parents=True, exist_ok=True)
    wanted = set(types)
    with httpx.Client(timeout=httpx.Timeout(60.0), follow_redirects=True) as client:
        days = [*SAMPLE_DAYS, latest_complete_day(now, client).isoformat()]
        audits: list[HourAudit] = []
        for day in dict.fromkeys(days):
            cache = cache_dir / f"{day}-{SAMPLE_HOUR}.json"
            if cache.exists():
                audits.append(HourAudit.from_json(json.loads(cache.read_text())))
                continue
            d = date.fromisoformat(day)
            ts = datetime(d.year, d.month, d.day, SAMPLE_HOUR)
            res = download_hour(ts, raw_dir, client=client)
            if res.status != "ok" or res.path is None:
                raise RuntimeError(f"audit sample {ts} unavailable: {res.status} {res.error}")
            log.info("auditing %s (%.1f MB)", day, res.size_bytes / 1e6)
            a = audit_file(
                res.path,
                day,
                SAMPLE_HOUR,
                wanted,
                fixture_out=fixture_dir / f"gharchive_{day}-{SAMPLE_HOUR}.sample.json.gz",
            )
            cache.write_text(json.dumps(a.to_json()))
            if not keep_raw:
                res.path.unlink(missing_ok=True)
            audits.append(a)
    docs_path.write_text(render_markdown(audits, types, now.date()), encoding="utf-8")
    return docs_path
