from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from huggingface_hub.errors import HfHubHTTPError

from breakout.lake import hf


class _Http(HfHubHTTPError):
    def __init__(self, code: int) -> None:
        Exception.__init__(self, f"HTTP {code}")
        self.response = SimpleNamespace(status_code=code)


def _files(tmp_path: Path, n: int, size: int = 10) -> list[hf.UploadItem]:
    out = []
    for i in range(n):
        p = tmp_path / f"f{i}.parquet"
        p.write_bytes(bytes([i]) * size)
        out.append(
            hf.UploadItem(p, f"events/f{i}.parquet", hashlib.sha256(p.read_bytes()).hexdigest())
        )
    return out


def test_ensure_repos_creates_four_public_repos(cfg, api):
    got = hf.ensure_repos(cfg, api)
    assert set(got) == {"events", "derived", "snapshots", "models"}
    assert all(private is False for _, _, private in api.created)
    types = {rid: t for rid, t, _ in api.created}
    assert types["u/models"] == "model" and types["u/events"] == "dataset"
    hf.ensure_repos(cfg, api)  # idempotent
    assert len(api.repos) == 4


def test_upload_batches_by_file_count(cfg, api, tmp_path):
    items = _files(tmp_path, 7)  # max_files_per_commit = 3 in the test config
    commits = hf.upload_files(api, cfg, "events", items, "push")
    assert len(commits) == 3
    assert [len(c["adds"]) for c in api.commits] == [3, 3, 1]
    assert api.commits[0]["msg"] == "push [1/3]"


def test_upload_batches_by_bytes(cfg, api, tmp_path, write_config):
    cfg.huggingface.max_bytes_per_commit = 25
    items = _files(tmp_path, 4, size=10)  # 2 files (20 B) fit, the 3rd would make 30 B
    hf.upload_files(api, cfg, "events", items, "push")
    assert [len(c["adds"]) for c in api.commits] == [2, 2]


def test_upload_skips_unchanged_by_sha(cfg, api, tmp_path):
    items = _files(tmp_path, 3)
    remote = {items[0].path_in_repo: items[0].sha256, items[1].path_in_repo: "different"}
    hf.upload_files(api, cfg, "events", items, "push", remote_sha=remote)
    assert sorted(api.commits[0]["adds"]) == sorted(i.path_in_repo for i in items[1:])
    assert (
        hf.upload_files(
            api, cfg, "events", items, "again", remote_sha={i.path_in_repo: i.sha256 for i in items}
        )
        == []
    )


def test_deletes_ride_in_the_last_commit_only(cfg, api, tmp_path):
    items = _files(tmp_path, 5)
    api.repos["u/events"] = {"events/old.parquet": b"x"}
    hf.upload_files(api, cfg, "events", items, "push", deletes=["events/old.parquet"])
    assert api.commits[0]["deletes"] == [] and api.commits[-1]["deletes"] == ["events/old.parquet"]
    assert "events/old.parquet" not in api.repos["u/events"]


def test_single_batch_add_and_delete_is_atomic(cfg, api, tmp_path):
    items = _files(tmp_path, 2)
    api.repos["u/events"] = {"events/old.parquet": b"x"}
    hf.upload_files(api, cfg, "events", items, "compact", deletes=["events/old.parquet"])
    assert len(api.commits) == 1
    assert len(api.commits[0]["adds"]) == 2 and api.commits[0]["deletes"] == ["events/old.parquet"]


def test_snapshots_repo_is_protected(cfg, api, tmp_path):
    with pytest.raises(ValueError, match="protected"):
        hf.upload_files(api, cfg, "snapshots", _files(tmp_path, 1), "x", deletes=["a"])
    with pytest.raises(ValueError, match="protected"):
        hf.commit_files(api, cfg, "snapshots", [], "x", deletes=["a"])


def test_retries_on_5xx_and_429_then_succeeds(cfg, api, tmp_path):
    api.fail_next = [_Http(503), _Http(429)]
    items = _files(tmp_path, 1)
    assert len(hf.upload_files(api, cfg, "events", items, "push")) == 1


def test_does_not_retry_client_errors(cfg, api, tmp_path):
    api.fail_next = [_Http(403)]
    with pytest.raises(HfHubHTTPError):
        hf.upload_files(api, cfg, "events", _files(tmp_path, 1), "push")


def test_remote_list_prefix_and_sha(cfg, api):
    api.repos["u/events"] = {"events/a.parquet": b"aa", "manifests/m.json": b"{}"}
    got = hf.remote_list(api, cfg, "events", "manifests")
    assert [f.path for f in got] == ["manifests/m.json"]
    assert hf.remote_list(api, cfg, "events")[0].sha256 == hashlib.sha256(b"aa").hexdigest()


def test_download_skips_matching_local_and_verifies_sha(cfg, api, tmp_path):
    data = b"hello parquet"
    sha = hashlib.sha256(data).hexdigest()
    api.repos["u/events"] = {"events/a.parquet": data, "events/b.parquet": b"bb"}
    root = tmp_path / "lake"
    (root / "events").mkdir(parents=True)
    (root / "events/a.parquet").write_bytes(data)  # already present and identical
    expected = {
        "events/a.parquet": (len(data), sha),
        "events/b.parquet": (2, hashlib.sha256(b"bb").hexdigest()),
    }
    out = hf.download_files(api, cfg, "events", list(expected), root, expected=expected)
    assert [p.name for p in out] == ["a.parquet", "b.parquet"]
    assert api.downloads == ["events/b.parquet"]
    bad = {"events/b.parquet": (2, "0" * 64)}
    (root / "events/b.parquet").unlink()
    with pytest.raises(OSError, match="sha256 mismatch"):
        hf.download_files(api, cfg, "events", ["events/b.parquet"], root, expected=bad)


def test_put_small_files_only_when_changed(cfg, api, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("v1")
    item = hf.UploadItem(readme, "README.md")
    assert hf.put_small_files(api, cfg, "events", [item], "card") is not None
    assert hf.put_small_files(api, cfg, "events", [item], "card") is None
    readme.write_text("v2")
    assert hf.put_small_files(api, cfg, "events", [item], "card") is not None
    assert len(api.commits) == 2


def test_hf_home_points_at_data_disk():
    import os

    from breakout.paths import DATA_DIR

    # set before huggingface_hub is imported unless the user already chose a location
    assert os.environ["HF_HOME"] == str(DATA_DIR / "hf_home") or os.environ.get("HF_HOME")
