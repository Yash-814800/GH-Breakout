"""Hugging Face Hub access for the lake: repos, batched atomic uploads, selective downloads.

Everything that touches the Hub goes through :func:`get_api`, so tests can inject a fake
``HfApi``. The Hugging Face cache lives on the data disk (``data/hf_home``, the Lexar SSD on the
dev machine) instead of ``~/.cache``: ``HF_HOME`` is set before ``huggingface_hub`` is imported.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from breakout.paths import DATA_DIR

os.environ.setdefault("HF_HOME", str(DATA_DIR / "hf_home"))

import httpx  # noqa: E402
from huggingface_hub import (  # noqa: E402
    CommitOperationAdd,
    CommitOperationDelete,
    HfApi,
)
from huggingface_hub.errors import (  # noqa: E402
    EntryNotFoundError,
    HfHubHTTPError,
    RepositoryNotFoundError,
    RevisionNotFoundError,
)
from tenacity import (  # noqa: E402
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from breakout.config import Config, MissingConfigError  # noqa: E402
from breakout.logging import get_logger  # noqa: E402

log = get_logger(__name__)

# config key -> (HuggingFaceCfg attribute, repo_type)
REPOS: dict[str, tuple[str, str]] = {
    "events": ("events_repo", "dataset"),
    "derived": ("derived_repo", "dataset"),
    "snapshots": ("snapshots_repo", "dataset"),
    "models": ("models_repo", "model"),
}
PROTECTED_REPOS = {"snapshots"}  # never delete or squash (CLAUDE.md, phase rules)
CATALOG_PATH = "catalog.parquet"


class CommitConflict(RuntimeError):
    """The repo head moved between reading the catalog and committing (HTTP 412)."""


def get_api(token: str | None = None) -> HfApi:
    token = token or os.environ.get("HF_TOKEN")
    if not token:
        raise MissingConfigError("HF_TOKEN is not set")
    return HfApi(token=token)


def repo_id(cfg: Config, key: str) -> str:
    attr, _ = REPOS[key]
    return getattr(cfg.huggingface, f"require_{attr}")()


def repo_type(key: str) -> str:
    return REPOS[key][1]


def ensure_repos(cfg: Config, api: HfApi | None = None) -> dict[str, str]:
    """Create the four public repos if missing (idempotent). Returns key -> repo id."""
    api = api or get_api()
    out: dict[str, str] = {}
    for key, (_, rtype) in REPOS.items():
        rid = repo_id(cfg, key)
        api.create_repo(rid, repo_type=rtype, exist_ok=True, private=False)
        out[key] = rid
    return out


def _status(exc: BaseException) -> int | None:
    resp = getattr(exc, "response", None)
    return getattr(resp, "status_code", None)


def _transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError | ConnectionError | TimeoutError):
        return True
    if isinstance(exc, HfHubHTTPError):
        code = _status(exc)
        return code == 429 or (code is not None and code >= 500)
    return False


retrying = retry(
    retry=retry_if_exception(_transient),
    wait=wait_exponential(multiplier=2, min=2, max=120),
    stop=stop_after_attempt(6),
    reraise=True,
)


# ---- hashing -----------------------------------------------------------------------------------


class ShaCache:
    """sha256 cache keyed on (relative path, size, mtime_ns); persisted as JSON next to the lake."""

    def __init__(self, path: Path | None):
        self.path = path
        self._lock = threading.Lock()
        self._data: dict[str, list] = {}
        if path is not None and path.exists():
            try:
                self._data = json.loads(path.read_text())
            except (OSError, ValueError):
                self._data = {}

    def get(self, key: str, file: Path) -> str:
        st = file.stat()
        with self._lock:
            hit = self._data.get(key)
        if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
            return hit[2]
        digest = sha256_file(file)
        with self._lock:
            self._data[key] = [st.st_size, st.st_mtime_ns, digest]
        return digest

    def save(self) -> None:
        if self.path is None:
            return
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(self._data))
            os.replace(tmp, self.path)


def git_blob_sha1(path: Path) -> str:
    """Git blob id of a file, to compare small non-LFS files with ``RemoteFile.blob_id``."""
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()  # noqa: S324


def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


# ---- listing -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class RemoteFile:
    path: str
    size: int
    sha256: str | None  # LFS oid; None for small non-LFS files
    blob_id: str | None = None  # git blob sha1 (comparable via git_blob_sha1)


@retrying
def remote_list(api: HfApi, cfg: Config, key: str, prefix: str = "") -> list[RemoteFile]:
    """All files under ``prefix`` (recursive, paginated by the client). Missing prefix -> []."""
    out: list[RemoteFile] = []
    try:
        for item in api.list_repo_tree(
            repo_id(cfg, key),
            path_in_repo=prefix or None,
            recursive=True,
            repo_type=repo_type(key),
        ):
            if hasattr(item, "size") and not hasattr(item, "tree_id"):
                lfs = getattr(item, "lfs", None)
                out.append(
                    RemoteFile(item.path, item.size, lfs.sha256 if lfs else None, item.blob_id)
                )
    except (EntryNotFoundError, RepositoryNotFoundError, RevisionNotFoundError):
        return []
    return out


@retrying
def changed_small_files(
    api: HfApi, cfg: Config, key: str, items: Sequence[UploadItem]
) -> list[UploadItem]:
    """Items whose git blob id differs from (or is absent in) the remote: README, manifests."""
    if not items:
        return []
    try:
        infos = api.get_paths_info(
            repo_id(cfg, key), [it.path_in_repo for it in items], repo_type=repo_type(key)
        )
    except RepositoryNotFoundError:
        infos = []
    remote = {getattr(i, "path", None): getattr(i, "blob_id", None) for i in infos}
    return [it for it in items if remote.get(it.path_in_repo) != git_blob_sha1(it.local)]


def put_small_files(
    api: HfApi, cfg: Config, key: str, items: Sequence[UploadItem], message: str
) -> str | None:
    """Commit only the small files that changed (one commit). Returns the commit id or None."""
    todo = changed_small_files(api, cfg, key, items)
    if not todo:
        return None
    return commit_files(api, cfg, key, todo, message)


def repo_head(api: HfApi, cfg: Config, key: str) -> str | None:
    try:
        return api.repo_info(repo_id(cfg, key), repo_type=repo_type(key)).sha
    except RepositoryNotFoundError:
        return None


# ---- upload ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class UploadItem:
    local: Path
    path_in_repo: str
    sha256: str | None = None  # local sha; enables skip-if-unchanged


def _batches(items: Sequence[UploadItem], max_files: int, max_bytes: int) -> list[list[UploadItem]]:
    out: list[list[UploadItem]] = []
    cur: list[UploadItem] = []
    cur_bytes = 0
    for it in items:
        size = it.local.stat().st_size
        if cur and (len(cur) >= max_files or cur_bytes + size > max_bytes):
            out.append(cur)
            cur, cur_bytes = [], 0
        cur.append(it)
        cur_bytes += size
    if cur:
        out.append(cur)
    return out


@retrying
def _commit(api: HfApi, rid: str, rtype: str, ops: list, message: str, parent: str | None) -> str:
    try:
        info = api.create_commit(
            rid,
            ops,
            commit_message=message,
            repo_type=rtype,
            parent_commit=parent,
        )
    except HfHubHTTPError as exc:
        if _status(exc) == 412:
            raise CommitConflict(str(exc)) from exc
        raise
    return str(getattr(info, "oid", None) or getattr(info, "commit_url", ""))


def upload_files(
    api: HfApi,
    cfg: Config,
    key: str,
    items: Iterable[UploadItem],
    message: str,
    *,
    deletes: Sequence[str] = (),
    remote_sha: dict[str, str] | None = None,
) -> list[str]:
    """Upload ``items`` in commits of <= ``max_files_per_commit`` files / ``max_bytes_per_commit``.

    - Items whose ``sha256`` equals ``remote_sha[path_in_repo]`` are skipped (no API call per file).
    - ``deletes`` go into the **last** commit, after every add, so an interruption never loses data;
      when everything fits in one commit the add+delete is atomic.
    Returns the commit ids created (empty when there was nothing to do).
    """
    if key in PROTECTED_REPOS and deletes:
        raise ValueError(f"refusing to delete files in protected repo {key!r}")
    remote_sha = remote_sha or {}
    todo = [it for it in items if not (it.sha256 and remote_sha.get(it.path_in_repo) == it.sha256)]
    batches = _batches(
        todo, cfg.huggingface.max_files_per_commit, cfg.huggingface.max_bytes_per_commit
    )
    if not batches and deletes:
        batches = [[]]
    rid, rtype = repo_id(cfg, key), repo_type(key)
    commits: list[str] = []
    for i, batch in enumerate(batches):
        last = i == len(batches) - 1
        ops: list = [
            CommitOperationAdd(path_in_repo=it.path_in_repo, path_or_fileobj=str(it.local))
            for it in batch
        ]
        if last:
            ops.extend(CommitOperationDelete(path_in_repo=p) for p in deletes)
        if not ops:
            continue
        msg = message if len(batches) == 1 else f"{message} [{i + 1}/{len(batches)}]"
        commits.append(_commit(api, rid, rtype, ops, msg, None))
        log.info(
            "%s commit %d/%d: %d file(s), %.2f GB",
            key,
            i + 1,
            len(batches),
            len(batch),
            sum(it.local.stat().st_size for it in batch) / 1e9,
        )
    return commits


def commit_files(
    api: HfApi,
    cfg: Config,
    key: str,
    items: Sequence[UploadItem],
    message: str,
    *,
    deletes: Sequence[str] = (),
    parent: str | None = None,
) -> str:
    """One atomic commit (adds + deletes); ``parent`` turns a race into ``CommitConflict``."""
    if key in PROTECTED_REPOS and deletes:
        raise ValueError(f"refusing to delete files in protected repo {key!r}")
    ops: list = [
        CommitOperationAdd(path_in_repo=it.path_in_repo, path_or_fileobj=str(it.local))
        for it in items
    ]
    ops.extend(CommitOperationDelete(path_in_repo=p) for p in deletes)
    return _commit(api, repo_id(cfg, key), repo_type(key), ops, message, parent)


# ---- download ----------------------------------------------------------------------------------


@retrying
def _download_one(api: HfApi, cfg: Config, key: str, path: str, local_root: Path) -> Path:
    got = api.hf_hub_download(
        repo_id(cfg, key),
        path,
        repo_type=repo_type(key),
        local_dir=str(local_root),
    )
    return Path(got)


def download_files(
    api: HfApi,
    cfg: Config,
    key: str,
    paths: Sequence[str],
    local_root: Path,
    *,
    expected: dict[str, tuple[int, str]] | None = None,
    workers: int = 8,
    cache: ShaCache | None = None,
) -> list[Path]:
    """Download ``paths`` so the layout under ``local_root`` mirrors the repo.

    A file is skipped when it exists locally and, if ``expected[path] = (size, sha256)`` is
    given, matches both size and sha256. Returns local paths in the order of ``paths``.
    """
    expected = expected or {}
    local_root.mkdir(parents=True, exist_ok=True)

    def one(path: str) -> Path:
        dest = local_root / path
        want = expected.get(path)
        if dest.is_file():
            if want is None:
                return dest
            size, sha = want
            if dest.stat().st_size == size:
                got = cache.get(path, dest) if cache else sha256_file(dest)
                if got == sha:
                    return dest
        out = _download_one(api, cfg, key, path, local_root)
        if want is not None:
            _, sha = want
            got = sha256_file(out)
            if got != sha:
                raise OSError(f"{path}: sha256 mismatch after download ({got} != {sha})")
        return out

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(one, paths))
