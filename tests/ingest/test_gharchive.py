from __future__ import annotations

import gzip
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from breakout.ingest.gharchive import download_hour, hour_url


def test_hour_url_is_not_zero_padded() -> None:
    assert hour_url(datetime(2024, 6, 1, 0)) == "https://data.gharchive.org/2024-06-01-0.json.gz"
    assert hour_url(datetime(2024, 6, 1, 7)) == "https://data.gharchive.org/2024-06-01-7.json.gz"
    assert hour_url(datetime(2024, 6, 1, 23)) == "https://data.gharchive.org/2024-06-01-23.json.gz"


def test_hour_url_requires_whole_hour() -> None:
    with pytest.raises(ValueError):
        hour_url(datetime(2024, 6, 1, 12, 30))
    with pytest.raises(ValueError):
        hour_url(datetime(2024, 6, 1, 12, 0, 1))


def test_hour_url_converts_aware_timestamps_to_utc() -> None:
    plus2 = timezone(timedelta(hours=2))
    assert hour_url(datetime(2024, 6, 1, 14, tzinfo=plus2)).endswith("2024-06-01-12.json.gz")
    assert hour_url(datetime(2024, 6, 1, 12, tzinfo=UTC)).endswith("2024-06-01-12.json.gz")


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


TS = datetime(2024, 6, 1, 5)


def test_download_ok(tmp_path: Path) -> None:
    payload = gzip.compress(b'{"id":"1"}\n')

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/2024-06-01-5.json.gz"
        return httpx.Response(200, content=payload)

    res = download_hour(TS, tmp_path, client=_client(handler), wait_min=0.001)
    assert res.status == "ok" and res.path is not None and res.path.exists()
    assert res.size_bytes == len(payload)
    assert len(res.sha256 or "") == 64
    assert not list(tmp_path.glob("*.part"))


def test_404_is_missing_and_not_retried(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404)

    res = download_hour(TS, tmp_path, client=_client(handler), wait_min=0.001)
    assert res.status == "missing"
    assert calls == 1
    assert list(tmp_path.iterdir()) == []


def test_5xx_is_retried_then_succeeds(tmp_path: Path) -> None:
    calls = 0
    payload = gzip.compress(b"x\n")

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503) if calls < 3 else httpx.Response(200, content=payload)

    res = download_hour(TS, tmp_path, client=_client(handler), wait_min=0.001)
    assert res.status == "ok" and res.attempts == 3


def test_persistent_5xx_gives_error_after_five_attempts(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    res = download_hour(TS, tmp_path, client=_client(handler), wait_min=0.001)
    assert res.status == "error" and calls == 5


def test_truncated_gzip_is_error_and_deleted(tmp_path: Path) -> None:
    good = gzip.compress(b"line\n" * 5000)
    truncated = good[: len(good) // 2]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=truncated)

    res = download_hour(TS, tmp_path, client=_client(handler), max_attempts=2, wait_min=0.001)
    assert res.status == "error"
    assert list(tmp_path.iterdir()) == []
