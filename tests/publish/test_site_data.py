from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from breakout.config import get_config
from breakout.publish import site_data


def test_publish_site_data(tmp_path: Path, monkeypatch) -> None:
    # Point site public data directory to tmp_path
    monkeypatch.setattr(site_data, "SITE_DATA_DIR", tmp_path / "public" / "data")
    monkeypatch.setattr(
        site_data, "LEADERBOARD_JSON", tmp_path / "public" / "data" / "leaderboard.json"
    )
    monkeypatch.setattr(site_data, "STATUS_JSON", tmp_path / "public" / "data" / "status.json")

    # Create dummy predictions
    pred_path = tmp_path / "predictions_2024-06-03.parquet"
    rows = [
        {
            "snapshot_date": "2024-06-03",
            "repo_id": 101,
            "repo_name": "owner/top_repo",
            "rank": 1,
            "prob": 0.85,
            "raw_score": 0.92,
            "b1_rank": 2,
            "explanation": "Flagged because high velocity",
            "top_contribs": json.dumps({"stars_7d": 0.45, "growth": 0.2}),
            "model_version": "v20261019-test",
            "features_hash": "sha123",
            "schema_version": 1,
            "suspicion_score": None,
        },
        {
            "snapshot_date": "2024-06-03",
            "repo_id": 102,
            "repo_name": "owner/second_repo",
            "rank": 2,
            "prob": 0.72,
            "raw_score": 0.78,
            "b1_rank": 1,
            "explanation": "Flagged because stars",
            "top_contribs": json.dumps({"stars_3d": 0.3}),
            "model_version": "v20261019-test",
            "features_hash": "sha123",
            "schema_version": 1,
            "suspicion_score": None,
        },
    ]
    pq.write_table(pa.Table.from_pylist(rows), pred_path)

    cfg = get_config(None)
    f_lead, f_stat = site_data.publish_site_data(cfg, d=date(2024, 6, 3), pred_path=pred_path)

    assert f_lead.exists()
    assert f_stat.exists()

    lead_data = json.loads(f_lead.read_text())
    assert len(lead_data) == 2
    assert lead_data[0]["repo_name"] == "owner/top_repo"
    assert lead_data[0]["rank"] == 1
    assert lead_data[0]["prob"] == 0.85
    assert isinstance(lead_data[0]["top_contribs"], dict)
    assert lead_data[0]["top_contribs"]["stars_7d"] == 0.45

    stat_data = json.loads(f_stat.read_text())
    assert stat_data["snapshot_date"] == "2024-06-03"
    assert stat_data["n_leaderboard"] == 2
    assert "published_at" in stat_data
