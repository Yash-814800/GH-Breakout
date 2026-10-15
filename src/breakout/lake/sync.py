"""Push/pull between the local lake and the events repo, keeping ``catalog.parquet`` consistent.

Every commit that adds data also carries the updated catalog, and commits are guarded by
``parent_commit`` so two concurrent Actions jobs cannot overwrite each other's catalog rows: the
loser sees a conflict, re-reads the remote catalog (its already-committed files are then skipped)
and tries again.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Iterable, Sequence
from datetime import date
from pathlib import Path

import pyarrow as pa
from huggingface_hub import HfApi
from huggingface_hub.errors import EntryNotFoundError, RepositoryNotFoundError

from breakout.config import Config
from breakout.lake import catalog as cat
from breakout.lake import hf, layout
from breakout.logging import get_logger
from breakout.paths import TMP_DIR, ensure_dir

log = get_logger(__name__)
KEY = "events"
MANIFEST_PREFIX = "manifests"


def _tmpdir() -> Path:
    """Scratch space on the data disk (never /tmp, which is small on the dev machine)."""
    return Path(tempfile.mkdtemp(prefix="sync-", dir=ensure_dir(TMP_DIR)))


def fetch_remote_catalog(api: HfApi, cfg: Config) -> tuple[pa.Table, str | None]:
    """(remote catalog, head commit it was read at). Empty catalog when the repo has none yet."""
    head = hf.repo_head(api, cfg, KEY)
    empty = pa.Table.from_pylist([], schema=cat.CATALOG_SCHEMA)
    if head is None:
        return empty, None
    tmp = _tmpdir()
    try:
        got = api.hf_hub_download(
            hf.repo_id(cfg, KEY),
            hf.CATALOG_PATH,
            repo_type=hf.repo_type(KEY),
            revision=head,
            local_dir=str(tmp),
        )
    except (EntryNotFoundError, RepositoryNotFoundError):
        return empty, head
    return cat.read_catalog(Path(got)), head


def _write_tmp_catalog(table: pa.Table) -> Path:
    return cat.write_catalog(table, _tmpdir() / hf.CATALOG_PATH)


def small_items(root: Path, rel_paths: Iterable[str]) -> list[hf.UploadItem]:
    """Existing non-data files (manifests, README) under ``root`` as upload items."""
    return [hf.UploadItem(root / r, r) for r in rel_paths if (root / r).is_file()]


def push_files(
    api: HfApi,
    cfg: Config,
    root: Path,
    files: Sequence[Path],
    message: str,
    *,
    deletes: Sequence[str] = (),
    extra: Sequence[hf.UploadItem] = (),
    cache: hf.ShaCache | None = None,
    retries: int = 5,
    progress: Callable[[int, int, int], None] | None = None,
) -> list[str]:
    """Upload ``files`` (paths under ``root``) plus the refreshed catalog; delete ``deletes``.

    Skips files already present remotely with the same sha256 (per the remote catalog). ``extra``
    (small non-catalogued files such as manifests/README) go in the last commit when their git
    blob id differs from the remote. Returns commit ids; ``[]`` when nothing changed.
    """
    rows = cat.build_catalog(root, files=files, cache=cache)
    by_path = {r["path"]: r for r in rows.to_pylist()}
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        base, head = fetch_remote_catalog(api, cfg)
        remote_sha = dict(
            zip(base.column("path").to_pylist(), base.column("sha256").to_pylist(), strict=True)
        )
        todo = [
            hf.UploadItem(root / p, p, r["sha256"])
            for p, r in by_path.items()
            if remote_sha.get(p) != r["sha256"]
        ]
        extra_todo = hf.changed_small_files(api, cfg, KEY, extra)
        known = set(base.column("path").to_pylist())
        deletes_todo = [d for d in deletes if d in known]
        if not todo and not extra_todo and not deletes_todo:
            return []
        batches = hf._batches(
            todo, cfg.huggingface.max_files_per_commit, cfg.huggingface.max_bytes_per_commit
        ) or [[]]
        commits: list[str] = []
        table, parent = base, head
        try:
            for i, batch in enumerate(batches):
                last = i == len(batches) - 1
                new_rows = pa.Table.from_pylist(
                    [by_path[it.path_in_repo] for it in batch], schema=cat.CATALOG_SCHEMA
                )
                table = cat.merge_catalogs(table, new_rows, deletes_todo if last else ())
                items = [*batch, hf.UploadItem(_write_tmp_catalog(table), hf.CATALOG_PATH)]
                if last:
                    items.extend(extra_todo)
                msg = message if len(batches) == 1 else f"{message} [{i + 1}/{len(batches)}]"
                parent = hf.commit_files(
                    api,
                    cfg,
                    KEY,
                    items,
                    msg,
                    deletes=deletes_todo if last else (),
                    parent=parent,
                )
                commits.append(parent)
                if progress:
                    progress(i + 1, len(batches), sum(it.local.stat().st_size for it in batch))
            return commits
        except hf.CommitConflict as exc:
            last_error = exc
            log.warning("commit conflict (attempt %d/%d); re-reading catalog", attempt, retries)
    raise RuntimeError(f"push failed after {retries} conflicts") from last_error


def select_remote(
    catalog: pa.Table,
    *,
    types: Sequence[str] | None,
    start: date | None,
    end: date | None,
    push_daily: bool,
) -> list[str]:
    paths: list[str] = []
    if types is None or len(types) > 0:
        paths += cat.select_files(catalog, cat.EVENTS_TABLE, types, start, end)
    if push_daily:
        paths += cat.select_files(catalog, cat.PUSH_TABLE, None, start, end)
    return paths


def pull(
    api: HfApi,
    cfg: Config,
    *,
    types: Sequence[str] | None,
    start: date | None,
    end: date | None,
    push_daily: bool = False,
    to: Path | None = None,
    workers: int = 8,
    manifests: bool = False,
) -> list[Path]:
    """Download exactly the files covering ``[start, end]`` for ``types`` into ``to``
    (default: the local lake root). Returns the local paths."""
    root = to or layout.lake_root(cfg)
    remote, _ = fetch_remote_catalog(api, cfg)
    paths = select_remote(remote, types=types, start=start, end=end, push_daily=push_daily)
    meta = {r["path"]: (r["bytes"], r["sha256"]) for r in remote.to_pylist()}
    cache = hf.ShaCache(root.parent / "catalog_cache.json")
    out = hf.download_files(
        api,
        cfg,
        KEY,
        paths,
        root,
        expected={p: meta[p] for p in paths},
        workers=workers,
        cache=cache,
    )
    cache.save()
    if manifests:
        mpaths = [f.path for f in hf.remote_list(api, cfg, KEY, MANIFEST_PREFIX)]
        out += hf.download_files(api, cfg, KEY, mpaths, root, workers=workers)
    return out
