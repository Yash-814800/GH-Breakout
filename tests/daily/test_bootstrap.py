"""Manifest fragment merge used by the clean-runner bootstrap."""

from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from breakout.config import get_config
from breakout.daily import bootstrap
from breakout.ingest.manifest import MANIFEST_SCHEMA, HourlyManifest


def _fragment(path: Path, hours: list[int], status: str) -> Path:
    rows = [{"hour_ts": datetime(2026, 10, 1, h), "status": status} for h in hours]
    pq.write_table(pa.Table.from_pylist(rows, schema=MANIFEST_SCHEMA), path)
    return path


def test_merge_manifest_fragments_is_idempotent_and_later_wins(tmp_path, monkeypatch):
    cfg = get_config(None)
    target = tmp_path / "hourly_manifest.parquet"
    monkeypatch.setattr(bootstrap.layout, "hourly_manifest_path", lambda _cfg=None: target)
    a = _fragment(tmp_path / "a.parquet", [0, 1], "missing")
    b = _fragment(tmp_path / "b.parquet", [1, 2], "ok")

    assert bootstrap.merge_manifest_fragments(cfg, [a, b]) == 4
    assert bootstrap.merge_manifest_fragments(cfg, [a, b]) == 4
    rows = HourlyManifest(target).load()
    assert sorted(h.hour for h in rows) == [0, 1, 2]
    assert rows[datetime(2026, 10, 1, 1)].status == "ok"
