"""Upload the training table to the derived Hugging Face repo under ``training/`` (Phase 7)."""

from __future__ import annotations

from typing import Any

from breakout.config import Config
from breakout.features.build import FEATURES_LABELS_DIR, HF_PREFIX, MANIFEST_PATH, TRAINING_DIR
from breakout.logging import get_logger

log = get_logger(__name__)


def upload_training(cfg: Config, api: Any | None = None) -> dict[str, Any]:
    """Upload year files + manifest; files whose sha256 already matches the remote are skipped."""
    from breakout.lake import hf

    api = api or hf.get_api()
    files = sorted(FEATURES_LABELS_DIR.glob("year=*/part-0.parquet")) + [MANIFEST_PATH]
    remote = {r.path: r for r in hf.remote_list(api, cfg, "derived", HF_PREFIX)}
    items = []
    for local in files:
        rel = f"{HF_PREFIX}/{local.relative_to(TRAINING_DIR).as_posix()}"
        sha = hf.sha256_file(local)
        r = remote.get(rel)
        if r is not None and r.sha256 == sha:
            continue
        if r is not None and r.sha256 is None and r.blob_id == hf.git_blob_sha1(local):
            continue
        items.append(hf.UploadItem(local=local, path_in_repo=rel, sha256=sha))
    if not items:
        return {"uploaded": [], "commits": 0}
    commits = hf.upload_files(api, cfg, "derived", items, "training: update features and labels")
    return {"uploaded": [i.path_in_repo for i in items], "commits": len(commits)}
