"""Download hourly GH Archive files (``YYYY-MM-DD-H.json.gz``; the hour is NOT zero-padded)."""

from __future__ import annotations

import gzip
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from breakout.logging import get_logger

log = get_logger(__name__)

BASE_URL = "https://data.gharchive.org"
Status = Literal["ok", "missing", "error"]


@dataclass(frozen=True)
class DownloadResult:
    status: Status
    path: Path | None = None
    sha256: str | None = None
    size_bytes: int = 0
    attempts: int = 1
    error: str | None = None
    source_host: str | None = None  # name of the configured source that served the file
    expected_events: int | None = None  # from the source's manifest, when configured and present
    expected_sha256: str | None = None
    integrity: str = "not_checked"  # ok | mismatch | unavailable | not_checked


class _Retryable(Exception):
    """Transient failure (5xx, timeout, transport error, truncated stream)."""


def _check_hour(ts: datetime) -> datetime:
    if ts.tzinfo is not None:
        ts = ts.astimezone(UTC).replace(tzinfo=None)
    if ts.minute or ts.second or ts.microsecond:
        raise ValueError(f"timestamp must be a whole UTC hour, got {ts.isoformat()}")
    return ts


def hour_url(ts: datetime, base_url: str = BASE_URL) -> str:
    ts = _check_hour(ts)
    return f"{base_url.rstrip('/')}/{ts:%Y-%m-%d}-{ts.hour}.json.gz"


def manifest_url(ts: datetime, base_url: str) -> str:
    """Per-hour manifest (OpenDigger convention): ``<base>/YYYY-MM-DD-H.manifest.json``."""
    ts = _check_hour(ts)
    return f"{base_url.rstrip('/')}/{ts:%Y-%m-%d}-{ts.hour}.manifest.json"


def hour_filename(ts: datetime) -> str:
    ts = _check_hour(ts)
    return f"{ts:%Y-%m-%d}-{ts.hour}.json.gz"


def verify_gzip(path: Path) -> None:
    """Read through the whole gzip stream once; raises on truncation/corruption."""
    with gzip.open(path, "rb") as fh:
        while fh.read(1 << 20):
            pass


def _attempt(client: httpx.Client, url: str, tmp: Path) -> tuple[Status, str | None, int]:
    sha = hashlib.sha256()
    size = 0
    try:
        with client.stream("GET", url) as resp:
            if resp.status_code == 404:
                return "missing", None, 0
            if resp.status_code >= 500 or resp.status_code == 429:
                raise _Retryable(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            with open(tmp, "wb") as out:
                for chunk in resp.iter_bytes(1 << 20):
                    out.write(chunk)
                    sha.update(chunk)
                    size += len(chunk)
    except (httpx.TransportError, httpx.TimeoutException) as exc:
        raise _Retryable(str(exc)) from exc
    return "ok", sha.hexdigest(), size


def download_hour(
    ts: datetime,
    dest_dir: Path,
    *,
    base_url: str = BASE_URL,
    client: httpx.Client | None = None,
    max_attempts: int = 5,
    wait_min: float = 1.0,
) -> DownloadResult:
    """Download one hour to ``dest_dir``. 404 -> ``missing``; truncated gzip -> ``error``."""
    url = hour_url(ts, base_url)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / hour_filename(ts)
    tmp = dest.with_name(dest.name + ".part")
    own_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(60.0), follow_redirects=True)
    attempts = 0

    @retry(
        retry=retry_if_exception(lambda e: isinstance(e, _Retryable)),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=wait_min, max=60),
        reraise=True,
    )
    def _fetch() -> tuple[Status, str | None, int]:
        nonlocal attempts
        attempts += 1
        status, sha, size = _attempt(client, url, tmp)
        if status == "ok":
            try:
                verify_gzip(tmp)
            except (OSError, EOFError, gzip.BadGzipFile) as exc:
                tmp.unlink(missing_ok=True)
                raise _Retryable(f"corrupt gzip: {exc}") from exc
        return status, sha, size

    try:
        status, sha, size = _fetch()
    except _Retryable as exc:
        tmp.unlink(missing_ok=True)
        log.warning("download failed for %s: %s", url, exc)
        return DownloadResult("error", None, None, 0, attempts, str(exc))
    except httpx.HTTPError as exc:
        tmp.unlink(missing_ok=True)
        log.warning("download failed for %s: %s", url, exc)
        return DownloadResult("error", None, None, 0, attempts, str(exc))
    finally:
        if own_client:
            client.close()
    if status == "missing":
        return DownloadResult("missing", None, None, 0, attempts)
    tmp.replace(dest)
    return DownloadResult("ok", dest, sha, size, attempts)


def fetch_manifest(
    ts: datetime, base_url: str, *, client: httpx.Client | None = None
) -> dict | None:
    """The source's per-hour manifest as a dict, or None (404, non-JSON, network error)."""
    own = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(20.0), follow_redirects=True)
    try:
        r = client.get(manifest_url(ts, base_url))
        if r.status_code != 200:
            return None
        data = r.json()
        return data if isinstance(data, dict) else None
    except (httpx.HTTPError, ValueError):
        return None
    finally:
        if own:
            client.close()


def _dig(obj: dict, dotted: str):
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def download_from_sources(
    ts: datetime,
    dest_dir: Path,
    sources: list,
    *,
    client: httpx.Client | None = None,
    **kwargs,
) -> DownloadResult:
    """Try ``sources`` (config ``SourceCfg`` objects) in priority order.

    The first source that returns a file wins. A manifest is consulted only for sources with
    ``has_manifest`` and ``manifest_keys`` configured (the key names are unverified until a
    manifest is actually observed, so nothing is guessed): the file sha256 must match, and the
    event count is returned for gap detection. All sources 404 -> ``missing``; otherwise a
    transport/integrity failure on every source -> ``error``.
    """
    last: DownloadResult | None = None
    saw_error = False
    for src in sources:
        res = download_hour(ts, dest_dir, base_url=src.base_url, client=client, **kwargs)
        if res.status == "ok":
            expected_events = expected_sha = None
            integrity = "not_checked"
            keys = getattr(src, "manifest_keys", None)
            if getattr(src, "has_manifest", False):
                man = fetch_manifest(ts, src.base_url, client=client)
                if man is None or not keys:
                    integrity = "unavailable"
                else:
                    expected_sha = _dig(man, keys.get("sha256", ""))
                    ev = _dig(man, keys.get("events", ""))
                    expected_events = (
                        int(ev) if isinstance(ev, int | str) and str(ev).isdigit() else None
                    )
                    if expected_sha and str(expected_sha).lower() != (res.sha256 or ""):
                        if res.path is not None:
                            res.path.unlink(missing_ok=True)
                        log.warning("%s sha256 mismatch for %s", src.name, ts)
                        last = DownloadResult(
                            "error",
                            None,
                            res.sha256,
                            res.size_bytes,
                            res.attempts,
                            "manifest sha256 mismatch",
                            src.name,
                            expected_events,
                            str(expected_sha),
                            "mismatch",
                        )
                        saw_error = True
                        continue
                    integrity = (
                        "ok" if (expected_sha or expected_events is not None) else "unavailable"
                    )
            return DownloadResult(
                "ok",
                res.path,
                res.sha256,
                res.size_bytes,
                res.attempts,
                None,
                src.name,
                expected_events,
                str(expected_sha) if expected_sha else None,
                integrity,
            )
        if res.status == "error":
            saw_error = True
        last = DownloadResult(res.status, None, None, 0, res.attempts, res.error, src.name)
    if last is None:
        return DownloadResult("error", error="no sources configured")
    if saw_error:
        return DownloadResult("error", None, None, 0, last.attempts, last.error, last.source_host)
    return DownloadResult("missing", None, None, 0, last.attempts, None, last.source_host)
