"""Upload enrichment outputs to the derived Hugging Face repo under ``enrich/`` (phase 4.6)."""

from __future__ import annotations

from typing import Any

from breakout.config import Config
from breakout.enrich.common import enrich_dir
from breakout.lake import hf

UPLOAD_FILES = (
    "repo_name_history.parquet",
    "repo_targets.parquet",
    "repo_metadata.parquet",
    "actor_age_samples.parquet",
    "actor_id_age_map.parquet",
    "trending.parquet",
    "hn_stories.parquet",
)
LFS_THRESHOLD = 10 * 1024 * 1024  # the Hub stores files above this as LFS (sha256 comparable)


def upload_enrich(cfg: Config, api: Any | None = None) -> dict[str, Any]:
    """Idempotent: files whose content already matches the remote are not re-uploaded.
    Commits are capped by ``huggingface.max_files_per_commit`` / ``max_bytes_per_commit``."""
    api = api or hf.get_api()
    root = enrich_dir(cfg)
    prefix = cfg.enrich.hf_prefix
    present = [n for n in UPLOAD_FILES if (root / n).is_file()]
    remote = {r.path: r for r in hf.remote_list(api, cfg, "derived", prefix)}
    items: list[hf.UploadItem] = []
    for name in present:
        local = root / name
        rel = f"{prefix}/{name}"
        sha = hf.sha256_file(local)
        r = remote.get(rel)
        if r is not None and r.sha256 == sha:
            continue
        if r is not None and r.sha256 is None and r.blob_id == hf.git_blob_sha1(local):
            continue
        items.append(hf.UploadItem(local=local, path_in_repo=rel, sha256=sha))
    commits = (
        hf.upload_files(api, cfg, "derived", items, "enrich: update derived enrichment tables")
        if items
        else []
    )
    return {
        "present": present,
        "uploaded": [i.path_in_repo for i in items],
        "commits": len(commits),
    }
