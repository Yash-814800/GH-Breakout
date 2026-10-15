"""Synthetic lake + in-memory fake Hugging Face API for Phase 3 tests."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from huggingface_hub.errors import EntryNotFoundError, HfHubHTTPError

from breakout.config import Config, load_config
from breakout.ingest import manifest as mf
from breakout.lake import layout, sync
from breakout.schema import EVENTS_SCHEMA, PUSH_DAILY_SCHEMA

TYPES = ["WatchEvent", "ForkEvent"]


@pytest.fixture
def cfg(write_config, tmp_path: Path) -> Config:
    def mutate(d: dict) -> None:
        d["lake"]["local_root"] = str(tmp_path / "data" / "lake")
        d["events"]["raw_types"] = list(TYPES)
        d["huggingface"]["events_repo"] = "u/events"
        d["huggingface"]["derived_repo"] = "u/derived"
        d["huggingface"]["snapshots_repo"] = "u/snapshots"
        d["huggingface"]["models_repo"] = "u/models"
        d["huggingface"]["max_files_per_commit"] = 3

    return load_config(write_config(mutate))


@pytest.fixture(autouse=True)
def _scratch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sync, "TMP_DIR", tmp_path / "scratch")
    import tenacity.nap

    monkeypatch.setattr(tenacity.nap.time, "sleep", lambda s: None)


def events_table(etype: str, day: date, n: int, *, source: str = "hourly", base_id: int = 0):
    rows = []
    for i in range(n):
        ts = datetime(day.year, day.month, day.day, (i * 7) % 24, i % 60)
        rows.append(
            {
                "event_id": base_id + i,
                "event_type": etype,
                "created_at": ts,
                "repo_id": (n - i) % 5 + 1,
                "repo_name": f"o/r{i % 5}",
                "actor_id": i,
                "actor_login": f"u{i}",
                "org_id": None,
                "detail_level": 1 if source == "hourly" else 0,
                "action": None,
                "number": None,
                "is_pull_request": None,
                "target_user_id": None,
                "target_created_at": None,
                "pr_merged": None,
                "review_state": None,
                "ref_type": None,
                "forkee_repo_id": None,
                "release_prerelease": None,
                "source": source,
                "ingested_at": datetime(2026, 1, 1),
            }
        )
    return pa.Table.from_pylist(rows, schema=EVENTS_SCHEMA)


def push_table(day: date, n: int):
    rows = [
        {
            "repo_id": i // 2 + 1,
            "actor_id": i,
            "day": day,
            "n_pushes": 1,
            "repo_name": "o/r",
            "source": "hourly",
            "ingested_at": datetime(2026, 1, 1),
        }
        for i in range(n)
    ]
    return pa.Table.from_pylist(rows, schema=PUSH_DAILY_SCHEMA)


class LakeBuilder:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.root = layout.lake_root(cfg)

    def day(self, day: date, n: int = 4, types=TYPES, base: int = 0) -> list[Path]:
        out = []
        for k, t in enumerate(types):
            p = layout.day_file(t, day, self.cfg)
            p.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(
                events_table(t, day, n, base_id=base + k * 1_000_000 + day.toordinal() * 10_000),
                p,
            )
            out.append(p)
        p = layout.day_file(layout.PUSH_TYPE, day, self.cfg)
        p.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(push_table(day, n), p)
        out.append(p)
        return out

    def bq(self, etype: str, year: int, month: int, n: int = 3) -> Path:
        p = layout.bq_file(etype, year, month, self.cfg)
        p.parent.mkdir(parents=True, exist_ok=True)
        t = events_table(etype, date(year, month, 5), n, source="bq")
        pq.write_table(t, p)
        return p

    def manifest(self, first: date, last_exclusive: date, ok_days: set[date]) -> None:
        rows = []
        h = datetime(first.year, first.month, first.day)
        end = datetime(last_exclusive.year, last_exclusive.month, last_exclusive.day)
        for ts in mf.iter_hours(h, end):
            rows.append(
                mf.ManifestRow(
                    ts, mf.OK if ts.date() in ok_days else mf.MISSING, 1, 1, "x", 1, ts, 2, "gh"
                )
            )
        mf.HourlyManifest(layout.hourly_manifest_path(self.cfg)).upsert(rows)


@pytest.fixture
def lake(cfg: Config) -> LakeBuilder:
    return LakeBuilder(cfg)


class _Err412(HfHubHTTPError):
    def __init__(self) -> None:  # bypass the response-requiring base constructor
        Exception.__init__(self, "412 precondition failed")
        self.response = SimpleNamespace(status_code=412)


class _ErrCode(HfHubHTTPError):
    def __init__(self, code: int) -> None:
        Exception.__init__(self, f"HTTP {code}")
        self.response = SimpleNamespace(status_code=code)


class FakeApi:
    """Minimal in-memory stand-in for ``HfApi`` (one dict of files per repo)."""

    def __init__(self) -> None:
        self.repos: dict[str, dict[str, bytes]] = {}
        self.heads: dict[str, int] = {}
        self.commits: list[dict] = []
        self.fail_next: list[BaseException] = []
        self.downloads: list[str] = []
        self.created: list[tuple[str, str, bool]] = []

    # --- repos
    def create_repo(self, repo_id, *, repo_type=None, exist_ok=False, private=None, **_):
        self.created.append((repo_id, repo_type, bool(private)))
        self.repos.setdefault(repo_id, {})
        self.heads.setdefault(repo_id, 0)

    def repo_info(self, repo_id, *, repo_type=None, **_):
        self.repos.setdefault(repo_id, {})
        self.heads.setdefault(repo_id, 0)
        return SimpleNamespace(sha=f"head{self.heads[repo_id]}")

    # --- commits
    def create_commit(
        self, repo_id, operations, *, commit_message, repo_type=None, parent_commit=None, **_
    ):
        if self.fail_next:
            raise self.fail_next.pop(0)
        files = self.repos.setdefault(repo_id, {})
        self.heads.setdefault(repo_id, 0)
        if parent_commit is not None and parent_commit != f"head{self.heads[repo_id]}":
            raise _Err412()
        adds, dels = [], []
        for op in operations:
            if op.__class__.__name__ == "CommitOperationAdd":
                files[op.path_in_repo] = Path(op.path_or_fileobj).read_bytes()
                adds.append(op.path_in_repo)
            else:
                files.pop(op.path_in_repo, None)
                dels.append(op.path_in_repo)
        self.heads[repo_id] += 1
        self.commits.append({"repo": repo_id, "adds": adds, "deletes": dels, "msg": commit_message})
        return SimpleNamespace(oid=f"head{self.heads[repo_id]}", commit_url="")

    # --- reads
    def list_repo_tree(self, repo_id, path_in_repo=None, *, recursive=False, repo_type=None, **_):
        for p, data in sorted(self.repos.get(repo_id, {}).items()):
            if path_in_repo and not p.startswith(path_in_repo.rstrip("/") + "/"):
                continue
            yield SimpleNamespace(
                path=p,
                size=len(data),
                blob_id="b",
                lfs=SimpleNamespace(sha256=hashlib.sha256(data).hexdigest()),
            )

    def get_paths_info(self, repo_id, paths, *, repo_type=None, **_):
        files = self.repos.get(repo_id, {})
        out = []
        for p in paths:
            if p in files:
                data = files[p]
                oid = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
                out.append(SimpleNamespace(path=p, blob_id=oid))
        return out

    def hf_hub_download(
        self, repo_id, filename, *, repo_type=None, local_dir=None, revision=None, **_
    ):
        files = self.repos.get(repo_id, {})
        if filename not in files:
            raise EntryNotFoundError("missing")
        self.downloads.append(filename)
        dest = Path(local_dir) / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(files[filename])
        return str(dest)


@pytest.fixture
def api() -> FakeApi:
    return FakeApi()
