from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from breakout.daily import run as daily_run
from breakout.ingest.manifest import HourlyManifest, ManifestRow


def test_heartbeat_generation(tmp_path: Path, monkeypatch) -> None:
    hb_path = tmp_path / "status" / "heartbeat.json"
    hb_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(daily_run, "HEARTBEAT_JSON_PATH", hb_path)

    # Write a test heartbeat
    hb_data = {
        "last_success_at": datetime.now(UTC).isoformat(),
        "snapshot_date": "2024-06-03",
        "model_version": "v1.0",
        "n_candidates": 42,
        "runtime_seconds": 12.3,
        "freeze_conflict": False,
        "dbt_freshness_passed": True,
        "missing_hours_older_than_3d": 0,
    }
    hb_path.write_text(json.dumps(hb_data, indent=2))

    read_back = json.loads(hb_path.read_text())
    assert read_back["snapshot_date"] == "2024-06-03"
    assert read_back["n_candidates"] == 42
    assert not read_back["freeze_conflict"]


def test_simulated_gap_planning(tmp_path: Path, monkeypatch) -> None:
    manifest_p = tmp_path / "hourly_manifest.parquet"
    manifest = HourlyManifest(manifest_p)

    # Ingest a few hours with hour 14 missing
    t1 = datetime(2024, 6, 3, 12, 0, 0)
    t2 = datetime(2024, 6, 3, 13, 0, 0)
    # Hour 14 is NOT recorded (gap!)
    t3 = datetime(2024, 6, 3, 15, 0, 0)

    manifest.upsert(
        [
            ManifestRow(hour_ts=t1, status="ok", parser_version=1),
            ManifestRow(hour_ts=t2, status="ok", parser_version=1),
            ManifestRow(hour_ts=t3, status="ok", parser_version=1),
        ]
    )

    # Plan for 2024-06-03
    now_dt = datetime(2024, 6, 4, 12, 0, 0)
    todo = manifest.hours_needing_work(
        datetime(2024, 6, 3, 0, 0, 0),
        datetime(2024, 6, 4, 0, 0, 0),
        now_dt,
        parser_version=1,
        min_hour_lag=3,
        late_hour_retry_days=3,
    )
    # Missing hours (including hour 14 and all unrecorded hours) are caught
    gap_hours = [h for h in todo if h == datetime(2024, 6, 3, 14, 0, 0)]
    assert len(gap_hours) == 1, "Expected missing hour 14:00 to be planned for ingest"


def test_adopt_frozen_snapshot_replaces_the_regenerated_file(tmp_path: Path) -> None:
    from breakout.daily.run import adopt_frozen_snapshot
    from breakout.ops import ledger

    frozen = tmp_path / "frozen.parquet"
    frozen.write_bytes(b"frozen-bytes")
    pred = tmp_path / "run" / "pred.parquet"
    pred.parent.mkdir()
    pred.write_bytes(b"regenerated")
    snap = tmp_path / "snap" / "predictions.parquet"
    snap.parent.mkdir()
    sha = adopt_frozen_snapshot(frozen, pred, snap)
    assert pred.read_bytes() == snap.read_bytes() == b"frozen-bytes"
    assert sha == ledger.file_sha256(frozen)
