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


class _Retryable(Exception):
    """Transient failure (5xx, timeout, transport error, truncated stream)."""


def _check_hour(ts: datetime) -> datetime:
    if ts.tzinfo is not None:
        ts = ts.astimezone(UTC).replace(tzinfo=None)
    if ts.minute or ts.second or ts.microsecond:
        raise ValueError(f"timestamp must be a whole UTC hour, got {ts.isoformat()}")
    return ts


def hour_url(ts: datetime) -> str:
    ts = _check_hour(ts)
    return f"{BASE_URL}/{ts:%Y-%m-%d}-{ts.hour}.json.gz"


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
    client: httpx.Client | None = None,
    max_attempts: int = 5,
    wait_min: float = 1.0,
) -> DownloadResult:
    """Download one hour to ``dest_dir``. 404 -> ``missing``; truncated gzip -> ``error``."""
    url = hour_url(ts)
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
