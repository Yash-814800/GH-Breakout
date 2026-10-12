from __future__ import annotations

import pytest

from breakout import paths


def test_repo_root_has_marker():
    assert (paths.ROOT / "CLAUDE.md").is_file()
    assert paths.DATA_DIR == paths.ROOT / "data"
    assert paths.WAREHOUSE == paths.DATA_DIR / "warehouse.duckdb"
    assert paths.MANIFEST_DIR.parent == paths.DATA_DIR


def test_find_repo_root_walks_up(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("x")
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    assert paths.find_repo_root(deep) == tmp_path.resolve()


def test_find_repo_root_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        paths.find_repo_root(tmp_path / "nowhere")


def test_ensure_dir_is_idempotent(tmp_path):
    target = tmp_path / "x" / "y"
    assert paths.ensure_dir(target) == target
    assert paths.ensure_dir(target) == target
    assert target.is_dir()
