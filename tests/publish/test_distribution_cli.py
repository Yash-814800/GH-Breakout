"""CLI and Hub plumbing of Phase 12 and 13 (the Hub is replaced by fakes)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from breakout import cli
from breakout.config import get_config
from breakout.lake import hf as hf_mod
from breakout.ops import ledger
from breakout.publish import dbt_docs
from breakout.publish import distribution as dist

runner = CliRunner()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = get_config(None)
    monkeypatch.setattr(cfg.site, "leaderboard_size", 3, raising=False)
    monkeypatch.setattr(dist, "SNAP_PRED", tmp_path / "snap" / "predictions")
    monkeypatch.setattr(dist, "SNAP_OUT", tmp_path / "snap" / "outcomes")
    monkeypatch.setattr(dist, "DATA_DIR", tmp_path / "pub" / "data")
    monkeypatch.setattr(dist, "BADGES_DIR", tmp_path / "pub" / "badges")
    monkeypatch.setattr(dist, "DIGESTS_DIR", tmp_path / "pub" / "data" / "digests")
    monkeypatch.setattr(dist, "FEED_ITEMS_JSON", tmp_path / "pub" / "data" / "feed_items.json")
    monkeypatch.setattr(dist, "_hidden", lambda: (set(), set()))
    monkeypatch.setattr(dist.ledger, "LEDGER_PATH", tmp_path / "ledger.csv")
    monkeypatch.setattr(dist.P, "TMP_DIR", tmp_path / "tmp")
    monkeypatch.setattr(cli, "get_config", lambda path=None: cfg)
    d = date(2026, 10, 19)
    p = dist.SNAP_PRED / f"date={d}" / "predictions.parquet"
    p.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "snapshot_date": d.isoformat(),
            "repo_id": [1, 2],
            "repo_name": ["a/one", "b/two"],
            "rank": [1, 2],
            "prob": [0.3, 0.2],
            "explanation": ["why", None],
            "suspicion_score": [None, None],
        }
    ).to_parquet(p)
    return cfg, tmp_path


class FakeHub:
    """Stands in for breakout.lake.hf: records uploads, serves files from a dict."""

    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.uploaded: list[str] = []

    def get_api(self):
        return object()

    def remote_list(self, api, cfg, key, prefix=""):
        return [
            hf_mod.RemoteFile(p, len(b), None)
            for p, b in self.files.items()
            if p.startswith(prefix)
        ]

    def download_files(self, api, cfg, key, paths, root):
        out = []
        for p in paths:
            f = Path(root) / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(self.files[p])
            out.append(f)
        return out

    def upload_files(self, api, cfg, key, items, message):
        self.uploaded += [i.path_in_repo for i in items]
        return ["c1"]

    UploadItem = hf_mod.UploadItem


def test_feeds_badges_and_digest_commands(env):
    r = runner.invoke(cli.app, ["publish", "feeds"])
    assert r.exit_code == 0, r.output
    assert json.loads(dist.FEED_ITEMS_JSON.read_text())[0]["repo_id"] in (1, 2)
    r = runner.invoke(cli.app, ["publish", "badges"])
    assert r.exit_code == 0 and (dist.BADGES_DIR / "1.json").exists()
    r = runner.invoke(cli.app, ["publish", "digest", "--week", "2026-W43"])
    assert r.exit_code == 0, r.output
    assert (dist.DIGESTS_DIR / "2026-W43.json").exists()
    assert (dist.DIGESTS_DIR / "index.json").exists()


def test_discuss_digest_dry_run_and_missing_file(env):
    r = runner.invoke(cli.app, ["publish", "discuss-digest", "--week", "2026-W43", "--dry-run"])
    assert r.exit_code == 1 and "No digest file" in r.output
    s, e = dist.parse_week("2026-W43")
    dist.write_digest(
        {
            "week": "2026-W43",
            "start": s.isoformat(),
            "end": e.isoformat(),
            "summary": "s.",
            "new_on_board": [],
            "movers": [],
            "matured": [],
            "notes": [],
        }
    )
    r = runner.invoke(cli.app, ["publish", "discuss-digest", "--week", "2026-W43", "--dry-run"])
    assert r.exit_code == 0 and "dry_run" in r.output and "Full issue:" in r.output
    r = runner.invoke(
        cli.app, ["publish", "discuss-digest", "--week", "2026-W43"], env={"GITHUB_TOKEN": ""}
    )
    assert r.exit_code == 1 and "GITHUB_TOKEN" in r.output


def test_restore_snapshots_downloads_only_missing_ledger_days(env, monkeypatch):
    cfg, root = env
    monkeypatch.setattr(
        ledger, "read_ledger", lambda: [{"date": "2026-10-19"}, {"date": "2026-10-20"}]
    )
    (root / "ledger.csv").write_text("x")
    hub = FakeHub({"predictions/date=2026-10-20/predictions.parquet": b"PAR1"})
    monkeypatch.setattr(dist.ledger, "read_ledger", ledger.read_ledger)
    import breakout.lake.hf as real_hf

    for name in ("get_api", "download_files"):
        monkeypatch.setattr(real_hf, name, getattr(hub, name))
    # download_files writes below P.DATA_DIR/snapshots; point it at the tmp dir
    monkeypatch.setattr(dist.P, "DATA_DIR", root / "datadir")
    got = dist.restore_snapshots(cfg, today=date(2026, 10, 21))
    assert got == 1  # 2026-10-19 already exists locally; only 10-20 was fetched
    assert (root / "datadir" / "snapshots" / "predictions" / "date=2026-10-20").exists()


def test_pull_and_upload_digests_and_site_facts(env, monkeypatch):
    cfg, root = env
    doc = {"week": "2026-W42", "start": "2026-10-12", "end": "2026-10-18", "summary": "s"}
    repo = {
        "repo_id": 7,
        "repo_name": "x/y",
        "metadata": {"primary_language": "Go"},
        "stars_total": 5,
    }
    hub = FakeHub(
        {
            "digests/2026-W42.json": json.dumps(doc).encode(),
            "digests/notes.txt": b"ignored",
            "site_data/latest/leaderboard.json": b"[]",
            "site_data/latest/meta.json": b"{}",
            "site_data/latest/repos/7.json": json.dumps(repo).encode(),
            "site_data/latest/other.json": b"{}",
        }
    )
    for name in ("get_api", "remote_list", "download_files", "upload_files"):
        monkeypatch.setattr(hf_mod, name, getattr(hub, name))
    assert dist.pull_digests(cfg) == 1
    idx = json.loads((dist.DIGESTS_DIR / "index.json").read_text())
    assert [m["week"] for m in idx] == ["2026-W42"]
    assert not list((dist.DIGESTS_DIR).glob("*.txt"))
    assert dist.upload_digests(cfg) == ["c1"]
    assert sorted(hub.uploaded) == ["digests/2026-W42.json", "digests/index.json"]
    assert dist.pull_site_facts(cfg) == 3
    assert not (dist.DATA_DIR / "other.json").exists()
    assert dist.repo_facts()[7]["language"] == "Go"
    assert dist.pull_site_facts(cfg) == 0  # leaderboard present: nothing to do


def test_pull_digests_survives_hub_errors(env, monkeypatch):
    cfg, _ = env

    def boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(hf_mod, "get_api", boom)
    assert dist.pull_digests(cfg) == 0
    assert dist.pull_site_facts(cfg) == 0


def test_dbt_docs_generate_uses_scratch_and_cleans_up(env, monkeypatch):
    cfg, root = env
    seen = {}

    def fake(cfg_, args, *, lake=None, warehouse=None, **kw):
        seen.update(args=args, lake=lake, warehouse=warehouse)
        assert Path(lake).is_dir()
        return 0

    monkeypatch.setattr(dbt_docs, "run_dbt", fake)
    dbt_docs.generate(cfg)
    assert seen["args"] == ["docs", "generate", "--empty-catalog"]
    assert not Path(seen["lake"]).exists()  # scratch removed
    monkeypatch.setattr(dbt_docs, "run_dbt", lambda *a, **k: 2)
    with pytest.raises(RuntimeError, match="exit code 2"):
        dbt_docs.generate(cfg)


def test_manifest_summary_counts():
    m = {
        "nodes": {
            "a": {"resource_type": "model", "columns": {"x": {}, "y": {}}},
            "b": {"resource_type": "model", "columns": {}},
            "t": {"resource_type": "test"},
            "s": {"resource_type": "seed"},
        }
    }
    assert dbt_docs.manifest_summary(m) == {"models": 2, "tests": 1, "columns": 2}
