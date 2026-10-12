from __future__ import annotations

import gzip
import hashlib
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from breakout.config import Config, SourceCfg, load_config
from breakout.ingest import manifest as mf
from breakout.ingest.day import ingest_day
from breakout.ingest.gharchive import (
    DownloadResult,
    download_from_sources,
    hour_url,
    manifest_url,
)
from breakout.lake import layout

TS = datetime(2026, 9, 12, 10)


def test_urls_use_base_url() -> None:
    assert hour_url(TS, "https://gharchive.open-digger.cn/") == (
        "https://gharchive.open-digger.cn/2026-09-12-10.json.gz"
    )
    assert manifest_url(TS, "https://gharchive.open-digger.cn") == (
        "https://gharchive.open-digger.cn/2026-09-12-10.manifest.json"
    )


def _sources(**manifest_kw) -> list[SourceCfg]:
    return [
        SourceCfg(name="opendigger", base_url="https://od.test", has_manifest=True, **manifest_kw),
        SourceCfg(name="gharchive", base_url="https://gh.test"),
    ]


def _client(routes: dict[str, httpx.Response]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(str(request.url), httpx.Response(404))

    return httpx.Client(transport=httpx.MockTransport(handler))


PAYLOAD = gzip.compress(b'{"id":"1"}\n')
SHA = hashlib.sha256(PAYLOAD).hexdigest()
OD = "https://od.test/2026-09-12-10"
GH = "https://gh.test/2026-09-12-10.json.gz"


def test_primary_source_wins_and_manifest_unavailable(tmp_path: Path) -> None:
    c = _client({OD + ".json.gz": httpx.Response(200, content=PAYLOAD)})
    r = download_from_sources(TS, tmp_path, _sources(), client=c, wait_min=0.001)
    assert (r.status, r.source_host, r.integrity) == ("ok", "opendigger", "unavailable")


def test_falls_back_when_primary_404(tmp_path: Path) -> None:
    c = _client({GH: httpx.Response(200, content=PAYLOAD)})
    r = download_from_sources(TS, tmp_path, _sources(), client=c, wait_min=0.001)
    assert (r.status, r.source_host) == ("ok", "gharchive")


def test_all_404_is_missing_and_5xx_everywhere_is_error(tmp_path: Path) -> None:
    r = download_from_sources(TS, tmp_path, _sources(), client=_client({}), wait_min=0.001)
    assert r.status == "missing"
    c = _client(
        {OD + ".json.gz": httpx.Response(503), GH: httpx.Response(503)},
    )
    r = download_from_sources(TS, tmp_path, _sources(), client=c, max_attempts=2, wait_min=0.001)
    assert r.status == "error"


def test_manifest_sha_and_event_count_used_when_keys_configured(tmp_path: Path) -> None:
    keys = {"sha256": "file.sha256", "events": "counts.total"}
    man = {"file": {"sha256": SHA}, "counts": {"total": 1}}
    c = _client(
        {
            OD + ".json.gz": httpx.Response(200, content=PAYLOAD),
            OD + ".manifest.json": httpx.Response(200, json=man),
        }
    )
    r = download_from_sources(TS, tmp_path, _sources(manifest_keys=keys), client=c, wait_min=0.001)
    assert r.integrity == "ok" and r.expected_events == 1 and r.expected_sha256 == SHA


def test_sha_mismatch_rejects_source_and_falls_back(tmp_path: Path) -> None:
    keys = {"sha256": "file.sha256", "events": "counts.total"}
    man = {"file": {"sha256": "0" * 64}, "counts": {"total": 1}}
    c = _client(
        {
            OD + ".json.gz": httpx.Response(200, content=PAYLOAD),
            OD + ".manifest.json": httpx.Response(200, json=man),
            GH: httpx.Response(200, content=PAYLOAD),
        }
    )
    r = download_from_sources(TS, tmp_path, _sources(manifest_keys=keys), client=c, wait_min=0.001)
    assert (r.status, r.source_host) == ("ok", "gharchive")


@pytest.fixture
def od_cfg(write_config, tmp_path: Path) -> Config:
    def mutate(d: dict) -> None:
        d["lake"]["local_root"] = str(tmp_path / "data" / "lake")
        d["ingest"]["sources"][0]["enabled"] = True

    return load_config(write_config(mutate))


def test_source_host_recorded_and_fallback_hours_retried_in_window(od_cfg: Config) -> None:
    from ingest_helpers import FakeDownloader, fixture_for

    day = date(2026, 9, 12)
    fx = fixture_for("2025-11-03")
    now = datetime(2026, 9, 13, 6)

    class Fallback(FakeDownloader):
        def __call__(self, ts, dest_dir, sources=None):
            res = super().__call__(ts, dest_dir, sources)
            assert [s.name for s in sources or []] == ["opendigger", "gharchive"]
            return DownloadResult(
                res.status, res.path, res.sha256, res.size_bytes, source_host="gharchive"
            )

    dl = Fallback(fx)
    s1 = ingest_day(day, cfg=od_cfg, now=now, downloader=dl)
    rows = mf.HourlyManifest(layout.hourly_manifest_path(od_cfg)).load()
    assert {r.source_host for r in rows.values()} == {"gharchive"}
    assert s1.hours_ok == 24
    # inside the window the preferred (opendigger) source is retried
    dl2 = Fallback(fx)
    ingest_day(day, cfg=od_cfg, now=now + timedelta(hours=2), downloader=dl2)
    assert len(dl2.calls) == 24
    # after the window the fallback result is accepted for good
    dl3 = Fallback(fx)
    ingest_day(day, cfg=od_cfg, now=now + timedelta(days=5), downloader=dl3)
    assert dl3.calls == []


def test_opendigger_rows_are_tagged_for_publish_exclusion(od_cfg: Config) -> None:
    import pyarrow.parquet as pq
    from ingest_helpers import FakeDownloader, fixture_for

    class OD(FakeDownloader):
        def __call__(self, ts, dest_dir, sources=None):
            res = super().__call__(ts, dest_dir, sources)
            return DownloadResult(
                res.status, res.path, res.sha256, res.size_bytes, source_host="opendigger"
            )

    day = date(2026, 9, 12)
    ingest_day(day, cfg=od_cfg, now=datetime(2026, 9, 14), downloader=OD(fixture_for("2025-11-03")))
    # the fixture's events are dated 2025-11-03, so they spill; read what was staged per hour
    staged = list((layout.staging_dir(od_cfg) / day.isoformat()).glob("hour=*.events.parquet"))
    assert staged
    assert {v for f in staged for v in pq.read_table(f).column("source").to_pylist()} == {
        "opendigger"
    }
    push = list((layout.staging_dir(od_cfg) / day.isoformat()).glob("hour=*.push.parquet"))
    assert {v for f in push for v in pq.read_table(f).column("source").to_pylist()} == {
        "opendigger"
    }
    rows = mf.HourlyManifest(layout.hourly_manifest_path(od_cfg)).load()
    assert {r.source_host for r in rows.values()} == {"opendigger"}
