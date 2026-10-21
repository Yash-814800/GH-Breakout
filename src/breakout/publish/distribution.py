"""Distribution (Phase 12): feed items, shields.io badges, weekly digest, Discussions post.

Everything here is derived from frozen prediction snapshots (``data/snapshots/predictions``),
their outcomes and the ledger, so the output is reproducible. Snapshots a clean runner lacks are
restored from the snapshots repo on the Hub (read only).

Outputs:
- ``site/public/data/feed_items.json``  (read by the endpoints ``/feed.xml`` and ``/feed.json``)
- ``site/public/badges/<repo_id>.json`` and ``badges/by-name/<owner>/<name>.json``
- ``site/public/data/digests/<week>.json`` + ``index.json`` (also on the derived repo)
"""

from __future__ import annotations

import json
import re
import urllib.parse
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from breakout import paths as P
from breakout.config import Config
from breakout.logging import get_logger
from breakout.ops import ledger

log = get_logger(__name__)

SITE_DIR = P.ROOT / "site"
DATA_DIR = SITE_DIR / "public" / "data"
BADGES_DIR = SITE_DIR / "public" / "badges"
FEED_ITEMS_JSON = DATA_DIR / "feed_items.json"
DIGESTS_DIR = DATA_DIR / "digests"
SNAP_PRED = P.DATA_DIR / "snapshots" / "predictions"
SNAP_OUT = P.DATA_DIR / "snapshots" / "outcomes"

SITE_URL = "https://yash-814800.github.io/GH-Breakout"
FEED_LIMIT = 100
NEW_ENTRY_WINDOW_DAYS = 30
BADGE_DAYS = 90
HORIZON_DAYS = 30
DIGEST_NEW_LIMIT = 10
DIGEST_MOVER_LIMIT = 8
DIGEST_MATURED_LIMIT = 25
MOVER_MIN_PLACES = 10
HIGH_SUSPICION = 90.0  # same cut-off the site uses for the "unusual pattern" badge
WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")

BADGE_LABEL = "breakout radar"
BADGE_NEUTRAL = "#9aa0a6"
# (minimum probability, colour): warmer means a higher chance. Contrast-safe on white text.
BADGE_COLOURS = ((0.25, "#c2410c"), (0.10, "#b45309"), (0.0, "#1d4ed8"))


# -----------------------------------------------------------------------------
# Snapshots
# -----------------------------------------------------------------------------


def _snap_path(d: date) -> Path:
    return SNAP_PRED / f"date={d.isoformat()}" / "predictions.parquet"


def _out_path(d: date) -> Path:
    return SNAP_OUT / f"date={d.isoformat()}" / "outcomes.parquet"


def ledger_dates() -> list[date]:
    if not ledger.LEDGER_PATH.exists():
        return []
    return sorted(date.fromisoformat(r["date"]) for r in ledger.read_ledger())


def restore_snapshots(
    cfg: Config, *, days: int = 125, outcomes: bool = False, today: date | None = None
) -> int:
    """Download frozen snapshots of the last ``days`` ledger days that are missing locally.

    Best effort: a day that cannot be fetched is skipped (and logged), never fatal. Returns the
    number of files fetched.
    """
    today = today or datetime.now(UTC).date()
    wanted = [d for d in ledger_dates() if (today - d).days <= days]
    jobs: list[tuple[str, Path]] = []
    for d in wanted:
        if not _snap_path(d).exists():
            jobs.append((f"predictions/date={d}/predictions.parquet", P.DATA_DIR / "snapshots"))
        if outcomes and not _out_path(d).exists():
            jobs.append((f"outcomes/date={d}/outcomes.parquet", P.DATA_DIR / "snapshots"))
    if not jobs:
        return 0
    from breakout.lake import hf as hf_mod

    api = hf_mod.get_api()
    got = 0
    for rel, root in jobs:
        try:
            hf_mod.download_files(api, cfg, "snapshots", [rel], root)
            got += 1
        except Exception as exc:  # missing outcomes are normal for recent days
            log.info("Snapshot file %s not restored (%s)", rel, type(exc).__name__)
    log.info("Restored %d/%d snapshot files from the Hub", got, len(jobs))
    return got


def load_board(cfg: Config) -> dict[date, pd.DataFrame]:
    """Top ``leaderboard_size`` rows of every local snapshot, by date, sorted by rank."""
    n = cfg.site.leaderboard_size
    out: dict[date, pd.DataFrame] = {}
    for p in sorted(SNAP_PRED.glob("date=*/predictions.parquet")):
        try:
            d = date.fromisoformat(p.parent.name.split("=")[-1])
            df = pd.read_parquet(p)
        except Exception as exc:
            log.warning("Unreadable snapshot %s: %s", p, exc)
            continue
        if "rank" not in df.columns and "raw_score" in df.columns:
            df = df.sort_values(["raw_score", "repo_id"], ascending=[False, True])
            df["rank"] = range(1, len(df) + 1)
        out[d] = df.sort_values(["rank", "repo_id"]).head(n).reset_index(drop=True)
    return out


def _hidden() -> tuple[set[int], set[str]]:
    from breakout.publish.site_data import load_hidden_repos

    return load_hidden_repos()


def _visible(df: pd.DataFrame) -> pd.DataFrame:
    from breakout.publish.site_data import is_repo_hidden

    ids, names = _hidden()
    keep = [
        not is_repo_hidden(int(r.repo_id), str(getattr(r, "repo_name", "") or ""), ids, names)
        for r in df.itertuples()
    ]
    return df[keep]


def new_entries(board: dict[date, pd.DataFrame]) -> list[dict[str, Any]]:
    """Repos entering the board for the first time in ``NEW_ENTRY_WINDOW_DAYS`` days.

    Entry on day D means: in the top N on D and in none of the snapshots dated in
    (D - 30 days, D). The first snapshot of the history counts as entries for every repo on it.
    """
    entries: list[dict[str, Any]] = []
    last_on: dict[int, date] = {}
    for d in sorted(board):
        for r in _visible(board[d]).itertuples():
            rid = int(r.repo_id)
            prev = last_on.get(rid)
            if prev is None or (d - prev).days >= NEW_ENTRY_WINDOW_DAYS:
                entries.append(
                    {
                        "repo_id": rid,
                        "repo_name": str(r.repo_name),
                        "date": d.isoformat(),
                        "rank": int(r.rank),
                        "prob": round(float(r.prob), 4),
                        "explanation": _clean(getattr(r, "explanation", None)),
                        "suspicion_score": _num(getattr(r, "suspicion_score", None)),
                    }
                )
            last_on[rid] = d
    return entries


def _clean(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s or None


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


# -----------------------------------------------------------------------------
# Repo facts (age, stars) from the exported site data
# -----------------------------------------------------------------------------


def _read_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def repo_facts(data_dir: Path | None = None) -> dict[int, dict[str, Any]]:
    """Display facts per repo id from ``leaderboard.json`` (preferred) and ``repos/*.json``."""
    root = data_dir or DATA_DIR
    facts: dict[int, dict[str, Any]] = {}
    repos = root / "repos"
    asof = _read_json(root / "meta.json") or {}
    end = asof.get("data_through")
    if repos.is_dir():
        for p in repos.glob("*.json"):
            d = _read_json(p)
            if not isinstance(d, dict):
                continue
            meta = d.get("metadata") or {}
            age = None
            if meta.get("created_at") and end:
                try:
                    created = datetime.fromisoformat(str(meta["created_at"]).replace("Z", "+00:00"))
                    age = max(0, (date.fromisoformat(end) - created.date()).days)
                except ValueError:
                    age = None
            facts[int(d["repo_id"])] = {
                "name": d.get("repo_name"),
                "language": meta.get("primary_language"),
                "owner_id": meta.get("owner_id"),
                "owner_type": meta.get("owner_type"),
                "stars_total": d.get("stars_total"),
                "age_days": age,
            }
    for row in _read_json(root / "leaderboard.json") or []:
        f = facts.setdefault(int(row["repo_id"]), {})
        if row.get("repo_name"):
            f["name"] = row["repo_name"]
        for src, dst in (
            ("language", "language"),
            ("owner_id", "owner_id"),
            ("owner_type", "owner_type"),
            ("stars_total_observed", "stars_total"),
            ("age_days", "age_days"),
            ("stars_gain_api", "stars_gain_7d"),
        ):
            if row.get(src) is not None:
                f[dst] = row[src]
        if (
            row.get("stars_7d")
            and "stars_gain_7d" not in f
            and row.get("stars_total_source") == ("gh_archive")
        ):
            f["stars_gain_7d"] = row["stars_7d"]
        f["suspicion_score"] = row.get("suspicion_score")
        f["suspicion_level"] = row.get("suspicion_level")
    return facts


# -----------------------------------------------------------------------------
# 12.1 Feed items
# -----------------------------------------------------------------------------


def display_name(repo_id: int, pred_name: str, facts: dict[int, dict[str, Any]]) -> str:
    """The snapshot name, or the name the published site data has when the snapshot lacks one."""
    if _name_parts(pred_name):
        return pred_name
    cand = facts.get(repo_id, {}).get("name")
    return str(cand) if cand and _name_parts(str(cand)) else pred_name


def _guid(repo_id: int, day: str) -> str:
    return f"{repo_id}:{day}"


def _suspicion_note(score: float | None) -> str | None:
    if score is not None and score >= HIGH_SUSPICION:
        return "Unusual star pattern: the star growth looks different from typical organic growth."
    return None


def build_feed_items(cfg: Config, *, previous: list[dict[str, Any]] | None = None) -> list[dict]:
    """Newest-first list (max ``FEED_LIMIT``) of new leaderboard entries.

    ``previous`` holds the items published earlier; their facts (age, stars) are kept because
    they were captured on the entry day and cannot be rebuilt later.
    """
    board = load_board(cfg)
    facts = repo_facts()
    kept = {it["guid"]: it for it in previous or []}
    items: dict[str, dict[str, Any]] = {}
    for e in new_entries(board):
        guid = _guid(e["repo_id"], e["date"])
        old = kept.get(guid)
        if old:
            items[guid] = old
            continue
        f = facts.get(e["repo_id"], {})
        score = (
            e["suspicion_score"] if e["suspicion_score"] is not None else f.get("suspicion_score")
        )
        items[guid] = {
            "guid": guid,
            "repo_id": e["repo_id"],
            "repo_name": display_name(e["repo_id"], e["repo_name"], facts),
            "date": e["date"],
            "rank": e["rank"],
            "prob": e["prob"],
            "explanation": e["explanation"],
            "age_days": f.get("age_days"),
            "stars_7d": f.get("stars_gain_7d"),
            "stars_total": f.get("stars_total"),
            "suspicion_note": _suspicion_note(score),
        }
    # items from earlier publications that the local history no longer reproduces stay in the feed
    for guid, old in kept.items():
        items.setdefault(guid, old)
    ordered = sorted(items.values(), key=lambda i: (i["date"], -i["rank"]), reverse=True)
    return ordered[:FEED_LIMIT]


def export_feed_items(cfg: Config) -> Path:
    previous = _read_json(FEED_ITEMS_JSON)
    items = build_feed_items(cfg, previous=previous if isinstance(previous, list) else None)
    FEED_ITEMS_JSON.parent.mkdir(parents=True, exist_ok=True)
    FEED_ITEMS_JSON.write_text(json.dumps(items, indent=2) + "\n")
    log.info("Wrote %d feed items to %s", len(items), FEED_ITEMS_JSON)
    return FEED_ITEMS_JSON


# -----------------------------------------------------------------------------
# 12.2 Badges
# -----------------------------------------------------------------------------


def badge_colour(prob: float) -> str:
    for floor, colour in BADGE_COLOURS:
        if prob >= floor:
            return colour
    return BADGE_COLOURS[-1][1]


def shields_payload(message: str, colour: str) -> dict[str, Any]:
    return {"schemaVersion": 1, "label": BADGE_LABEL, "message": message, "color": colour}


def _name_parts(repo_name: str) -> tuple[str, str] | None:
    """(owner, name) for a real GitHub name; None for ``repo_id=123`` placeholders."""
    if "=" in repo_name or repo_name.count("/") != 1:
        return None
    owner, name = repo_name.split("/")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", owner) or not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        return None
    if owner in (".", "..") or name in (".", ".."):
        return None
    return owner, name


def build_badges(cfg: Config, today: date | None = None) -> dict[int, dict[str, Any]]:
    """Badge payload and current name per repo flagged in the last ``BADGE_DAYS`` days.

    A repo is "on the board today" when it is in the top N of the newest snapshot. The badge
    never encodes suspicion.
    """
    board = load_board(cfg)
    if not board:
        return {}
    facts = repo_facts()
    latest = max(board)
    today = today or latest
    cutoff = today - timedelta(days=BADGE_DAYS)
    last_seen: dict[int, tuple[date, pd.Series]] = {}
    for d in sorted(board):
        if d < cutoff:
            continue
        for _, r in _visible(board[d]).iterrows():
            last_seen[int(r["repo_id"])] = (d, r)
    n = cfg.site.leaderboard_size
    out: dict[int, dict[str, Any]] = {}
    for rid, (d, r) in last_seen.items():
        if d == latest:
            message = f"#{int(r['rank'])} today · {round(float(r['prob']) * 100)}%"
            colour = badge_colour(float(r["prob"]))
        else:
            message = f"flagged {d.isoformat()}"
            colour = BADGE_NEUTRAL
        out[rid] = {
            "repo_name": display_name(rid, str(r["repo_name"]), facts),
            "payload": shields_payload(message, colour),
            "on_board": d == latest and int(r["rank"]) <= n,
        }
    return out


def export_badges(cfg: Config) -> list[Path]:
    """Write ``badges/<repo_id>.json`` and ``badges/by-name/<owner>/<name>.json``."""
    badges = build_badges(cfg)
    if BADGES_DIR.exists():
        for p in BADGES_DIR.rglob("*.json"):
            p.unlink()  # stale badges of repos no longer flagged in the window disappear
    written: list[Path] = []
    for rid, b in sorted(badges.items()):
        text = json.dumps(b["payload"]) + "\n"
        p = BADGES_DIR / f"{rid}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        written.append(p)
        parts = _name_parts(b["repo_name"])
        if parts:
            q = BADGES_DIR / "by-name" / parts[0].lower() / f"{parts[1].lower()}.json"
            q.parent.mkdir(parents=True, exist_ok=True)
            q.write_text(text)
            written.append(q)
    log.info("Wrote %d badge files to %s", len(written), BADGES_DIR)
    return written


def badge_markdown(repo_id: int, site_url: str = SITE_URL) -> str:
    """Markdown snippet for a README: a shields.io endpoint badge linking to the repo page."""
    badge_json = f"{site_url}/badges/{repo_id}.json"
    img = f"https://img.shields.io/endpoint?url={urllib.parse.quote(badge_json, safe='')}"
    return f"[![breakout radar]({img})]({site_url}/repo/{repo_id}/)"


# -----------------------------------------------------------------------------
# 12.3 Weekly digest
# -----------------------------------------------------------------------------


def parse_week(week: str) -> tuple[date, date]:
    m = WEEK_RE.match(week)
    if not m:
        raise ValueError(f"--week must look like 2026-W43, got {week!r}")
    start = date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
    return start, start + timedelta(days=6)


def iso_week(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def default_week(today: date | None = None) -> str:
    """The ISO week ending today when today is Sunday, otherwise the previous complete week."""
    today = today or datetime.now(UTC).date()
    return iso_week(
        today if today.isoweekday() == 7 else today - timedelta(days=today.isoweekday())
    )


def _repo_entry(
    repo_id: int, name: str, facts: dict[int, dict[str, Any]], **extra: Any
) -> dict[str, Any]:
    f = facts.get(repo_id, {})
    out = {
        "repo_id": repo_id,
        "repo_name": name,
        "language": f.get("language"),
        "age_days": f.get("age_days"),
        "stars_total": f.get("stars_total"),
        "owner_id": f.get("owner_id"),
        "owner_type": f.get("owner_type")
        if f.get("owner_type") in ("User", "Organization")
        else None,
    }
    out.update(extra)
    return out


def _model_notes(start: date, end: date) -> list[str]:
    rows = [r for r in ledger.read_ledger()] if ledger.LEDGER_PATH.exists() else []
    notes: list[str] = []
    in_week = [r for r in rows if start <= date.fromisoformat(r["date"]) <= end]
    if not in_week:
        return ["No list was frozen this week."]
    before = [r for r in rows if date.fromisoformat(r["date"]) < start]
    versions: list[str] = []
    prev = before[-1]["model_version"] if before else None
    for r in in_week:
        if r["model_version"] != prev:
            if prev is not None:
                notes.append(
                    f"The model changed from {prev} to {r['model_version']} on {r['date']}."
                )
            versions.append(r["model_version"])
            prev = r["model_version"]
    if not notes:
        notes.append(f"The model stayed at version {in_week[-1]['model_version']} all week.")
    frozen = {date.fromisoformat(r["date"]) for r in in_week}
    last = min(end, max(frozen))
    missing = [
        (start + timedelta(days=i)).isoformat()
        for i in range((last - start).days + 1)
        if (start + timedelta(days=i)) not in frozen and (start + timedelta(days=i)) >= min(frozen)
    ]
    if missing:
        notes.append("No list was frozen on " + ", ".join(missing) + ".")
    if end >= datetime.now(UTC).date():
        notes.append(f"{len(in_week)} daily lists were frozen in the ledger so far this week.")
    else:
        notes.append(f"{len(in_week)} of 7 daily lists were frozen in the ledger this week.")
    return notes


def _drift_notes(start: date, end: date) -> list[str]:
    """Drift flags from the weekly report committed under reports/retrain/ (if any)."""
    notes: list[str] = []
    for p in sorted((P.ROOT / "reports" / "retrain").glob("*.md")):
        try:
            d = date.fromisoformat(p.stem)
        except ValueError:
            continue
        if not (start <= d <= end):
            continue
        text = p.read_text()
        if re.search(r"drift[_ ]detected|PSI\s*>\s*0\.25", text, re.I):
            notes.append(f"The weekly drift check on {d.isoformat()} flagged feature drift.")
        elif re.search(r"drift", text, re.I):
            notes.append(f"The weekly drift check on {d.isoformat()} found no significant drift.")
    return notes


def build_digest(cfg: Config, week: str) -> dict[str, Any]:
    """Digest of one ISO week, from frozen snapshots, outcomes and the ledger only."""
    start, end = parse_week(week)
    board = load_board(cfg)
    facts = repo_facts()
    in_week = sorted(d for d in board if start <= d <= end)

    # 1. New on the board: entries in the week, top 10 by the highest probability that week
    # the first snapshot ever has nothing before it, so everything on it would look new
    first_day = min(board) if board else None
    entries = [
        e
        for e in new_entries(board)
        if start <= date.fromisoformat(e["date"]) <= end
        and date.fromisoformat(e["date"]) != first_day
    ]
    best: dict[int, dict[str, Any]] = {}
    for d in in_week:
        for r in _visible(board[d]).itertuples():
            rid = int(r.repo_id)
            if rid in {e["repo_id"] for e in entries} and (
                rid not in best or float(r.prob) > best[rid]["prob"]
            ):
                best[rid] = {
                    "prob": round(float(r.prob), 4),
                    "name": display_name(rid, str(r.repo_name), facts),
                    "explanation": _clean(getattr(r, "explanation", None)),
                }
    new_on = [
        _repo_entry(rid, b["name"], facts, prob=b["prob"], explanation=b["explanation"])
        for rid, b in sorted(best.items(), key=lambda kv: (-kv[1]["prob"], kv[0]))[
            :DIGEST_NEW_LIMIT
        ]
    ]

    # 2. Movers: ranks (among all candidates) of repos on the board on the last day of the week
    movers: list[dict[str, Any]] = []
    if len(in_week) >= 2:
        first_d, last_d = in_week[0], in_week[-1]
        first_all = pd.read_parquet(_snap_path(first_d), columns=["repo_id", "rank"])
        first_rank = dict(
            zip(first_all["repo_id"].astype(int), first_all["rank"].astype(int), strict=True)
        )
        cand = []
        for r in _visible(board[last_d]).itertuples():
            fr = first_rank.get(int(r.repo_id))
            if fr is not None and fr - int(r.rank) > MOVER_MIN_PLACES:
                cand.append(
                    (
                        fr - int(r.rank),
                        int(r.repo_id),
                        display_name(int(r.repo_id), str(r.repo_name), facts),
                        fr,
                        int(r.rank),
                    )
                )
        for _, rid, nm, fr, to in sorted(cand, reverse=True)[:DIGEST_MOVER_LIMIT]:
            movers.append(_repo_entry(rid, nm, facts, from_rank=fr, to_rank=to))

    # 3. Matured: lists from 30 days before each day of the week, judged with realised labels
    matured: list[dict[str, Any]] = []
    seen: set[int] = set()
    pool: list[dict[str, Any]] = []
    for i in range(7):
        pd_ = start + timedelta(days=i) - timedelta(days=HORIZON_DAYS)
        if not (_snap_path(pd_).exists() and _out_path(pd_).exists()):
            continue
        preds = pd.read_parquet(_snap_path(pd_))
        outs = pd.read_parquet(_out_path(pd_))
        m = preds.merge(outs, on="repo_id", how="inner").sort_values("rank")
        for r in _visible(m).head(cfg.site.leaderboard_size).itertuples():
            pool.append(
                {
                    "rank": int(r.rank),
                    "repo_id": int(r.repo_id),
                    "name": display_name(int(r.repo_id), str(r.repo_name), facts),
                    "prob": round(float(r.prob), 4),
                    "hit": bool(r.label) if pd.notna(r.label) else False,
                    "gain": _num(getattr(r, "gain_30d", None)),
                    "on": pd_.isoformat(),
                }
            )
    for row in sorted(pool, key=lambda x: (x["rank"], x["on"])):
        if row["repo_id"] in seen:
            continue
        seen.add(row["repo_id"])
        matured.append(
            _repo_entry(
                row["repo_id"],
                row["name"],
                facts,
                prob=row["prob"],
                hit=row["hit"],
                gain_30d=row["gain"],
                predicted_on=row["on"],
            )
        )
        if len(matured) >= DIGEST_MATURED_LIMIT:
            break

    notes = _model_notes(start, end) + _drift_notes(start, end)
    if first_day is not None and start <= first_day <= end:
        notes.append(
            f"Live lists start on {first_day.isoformat()}, so the repos on that first list are not "
            "counted as new."
        )
    if not matured:
        first = ledger_dates()[0] if ledger_dates() else None
        if first:
            ready = (first + timedelta(days=HORIZON_DAYS)).isoformat()
            notes.append(
                f"No prediction from 30 days ago exists to judge yet; the first live list was "
                f"frozen on "
                f"{first.isoformat()} and matures on {ready}."
            )
    if end > datetime.now(UTC).date():
        notes.append("This week is still in progress; the issue covers the days frozen so far.")

    hits = sum(1 for r in matured if r.get("hit"))
    parts = [
        f"{len(best)} repo{'s' if len(best) != 1 else ''} joined the list",
        f"{len(movers)} climbed more than {MOVER_MIN_PLACES} places",
        (
            f"{hits} of {len(matured)} matured predictions broke out"
            if matured
            else "no predictions have matured yet"
        ),
    ]
    summary = f"{parts[0]}, {parts[1]}, and {parts[2]}."
    return {
        "week": week,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "summary": summary,
        "new_on_board": new_on,
        "movers": movers,
        "matured": matured,
        "notes": notes,
    }


def write_digest(doc: dict[str, Any], out_dir: Path | None = None) -> Path:
    """Write ``<week>.json`` and rebuild ``index.json`` from every digest file in the folder."""
    root = out_dir or DIGESTS_DIR
    root.mkdir(parents=True, exist_ok=True)
    p = root / f"{doc['week']}.json"
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    rebuild_index(root)
    return p


def rebuild_index(root: Path | None = None) -> Path:
    root = root or DIGESTS_DIR
    metas = []
    for f in sorted(root.glob("*-W*.json")):
        d = _read_json(f)
        if isinstance(d, dict) and WEEK_RE.match(str(d.get("week", ""))):
            metas.append({k: d[k] for k in ("week", "start", "end", "summary")})
    idx = root / "index.json"
    idx.write_text(
        json.dumps(sorted(metas, key=lambda m: m["week"], reverse=True), indent=2) + "\n"
    )
    return idx


def upload_digests(cfg: Config) -> list[str]:
    """Store digest data on the derived repo under ``digests/`` (add or replace only)."""
    from breakout.lake import hf as hf_mod

    items = [hf_mod.UploadItem(f, f"digests/{f.name}") for f in sorted(DIGESTS_DIR.glob("*.json"))]
    if not items:
        return []
    return hf_mod.upload_files(hf_mod.get_api(), cfg, "derived", items, "digests: update")


def pull_site_facts(cfg: Config) -> int:
    """Fetch the published leaderboard, meta and repo pages (language, age, stars) from the Hub.

    The weekly runner has no site data of its own; the digest needs these display facts.
    Existing local files are kept. Best effort.
    """
    if (DATA_DIR / "leaderboard.json").exists():
        return 0
    import shutil

    from breakout.lake import hf as hf_mod

    try:
        api = hf_mod.get_api()
        prefix = "site_data/latest/"
        remote = [
            f.path
            for f in hf_mod.remote_list(api, cfg, "derived", prefix)
            if f.path.removeprefix(prefix) in ("leaderboard.json", "meta.json")
            or f.path.removeprefix(prefix).startswith("repos/")
        ]
        tmp = P.TMP_DIR / "site_facts"
        hf_mod.download_files(api, cfg, "derived", remote, tmp)
        shutil.copytree(tmp / prefix.rstrip("/"), DATA_DIR, dirs_exist_ok=True)
        return len(remote)
    except Exception as exc:
        log.warning("No site facts pulled (digest repos lack language and age): %s", exc)
        return 0


def pull_digests(cfg: Config) -> int:
    """Fetch ``digests/*.json`` of the derived repo into site/public/data/digests (best effort)."""
    from breakout.lake import hf as hf_mod

    try:
        api = hf_mod.get_api()
        remote = [
            f.path
            for f in hf_mod.remote_list(api, cfg, "derived", "digests/")
            if f.path.endswith(".json")
        ]
        if not remote:
            return 0
        hf_mod.download_files(api, cfg, "derived", remote, DATA_DIR)
        rebuild_index(DIGESTS_DIR)
        return len(remote)
    except Exception as exc:
        log.warning("No digests pulled (%s)", exc)
        return 0


# -----------------------------------------------------------------------------
# 12.5 GitHub Discussions
# -----------------------------------------------------------------------------


def digest_markdown(doc: dict[str, Any], site_url: str = SITE_URL) -> str:
    """Plain Markdown body of a digest for a GitHub Discussion (links to the site)."""
    L = [f"**{doc['week']}** ({doc['start']} to {doc['end']}). {doc['summary']}", ""]

    def repo(r: dict[str, Any]) -> str:
        label = r["repo_name"] if _name_parts(r["repo_name"]) else f"Repo {r['repo_id']}"
        link = f"[{label}]({site_url}/repo/{r['repo_id']}/)"
        prob = f" · {round(r['prob'] * 100)}%" if r.get("prob") is not None else ""
        return f"- {link}{prob}"

    if doc["new_on_board"]:
        L += ["### New on the list", *[repo(r) for r in doc["new_on_board"]], ""]
    if doc["movers"]:
        L += [
            "### Biggest movers",
            *[f"{repo(r)} · #{r['from_rank']} to #{r['to_rank']}" for r in doc["movers"]],
            "",
        ]
    if doc["matured"]:
        L += [
            "### Predictions that matured",
            *[
                f"{repo(r)} · {'broke out' if r.get('hit') else 'did not break out'}"
                for r in doc["matured"]
            ],
            "",
        ]
    if doc["notes"]:
        L += ["### Model and pipeline notes", *[f"- {n}" for n in doc["notes"]], ""]
    L.append(f"Full issue: {site_url}/digest/{doc['week']}/")
    return "\n".join(L)


def _graphql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    import httpx

    r = httpx.post(
        "https://api.github.com/graphql",
        json={"query": query, "variables": variables},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise RuntimeError("; ".join(e.get("message", "?") for e in body["errors"]))
    return body["data"]


def post_discussion(
    doc: dict[str, Any],
    *,
    repo: str,
    token: str,
    category: str = "Digest",
    fallback_category: str = "Announcements",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create the digest's Discussion once. Idempotent: an existing title is left alone.

    Uses the category named ``category``; GitHub has no API to create categories, so when it
    does not exist yet the post goes to ``fallback_category`` and the result says so.
    """
    owner, name = repo.split("/")
    title = f"Weekly digest {doc['week']}"
    body = digest_markdown(doc)
    if dry_run:
        return {"status": "dry_run", "title": title, "body": body}
    q = """
    query($o:String!,$n:String!){ repository(owner:$o,name:$n){
      id hasDiscussionsEnabled
      discussionCategories(first:25){ nodes{ id name } }
      discussions(first:50, orderBy:{field:CREATED_AT, direction:DESC}){ nodes{ title url } } } }"""
    data = _graphql(token, q, {"o": owner, "n": name})["repository"]
    if not data["hasDiscussionsEnabled"]:
        return {"status": "discussions_disabled", "title": title}
    for d in data["discussions"]["nodes"]:
        if d["title"] == title:
            return {"status": "exists", "title": title, "url": d["url"]}
    cats = {c["name"].lower(): c["id"] for c in data["discussionCategories"]["nodes"]}
    chosen = category if category.lower() in cats else fallback_category
    if chosen.lower() not in cats:
        return {"status": "no_category", "title": title, "categories": sorted(cats)}
    m = """
    mutation($r:ID!,$c:ID!,$t:String!,$b:String!){
      createDiscussion(input:{repositoryId:$r, categoryId:$c, title:$t, body:$b}){
        discussion{ url } } }"""
    res = _graphql(token, m, {"r": data["id"], "c": cats[chosen.lower()], "t": title, "b": body})
    return {
        "status": "created",
        "title": title,
        "category": chosen,
        "url": res["createDiscussion"]["discussion"]["url"],
    }
