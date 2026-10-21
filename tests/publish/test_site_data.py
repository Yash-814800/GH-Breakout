"""Unit tests for site-data publishing (Phase 10)."""

from pathlib import Path

import jsonschema
import pytest

from breakout.config import get_config
from breakout.publish import site_data


def test_prob_label_formatting():
    assert site_data.format_prob_label(0.5) == "~1 in 2"
    assert site_data.format_prob_label(0.25) == "~1 in 4"
    assert site_data.format_prob_label(0.1) == "~1 in 10"
    assert site_data.format_prob_label(0.005) == "< 1 in 100"
    assert site_data.format_prob_label(0.0) == "< 1 in 1000"


def test_hidden_repos_filtering(tmp_path: Path):
    cfg_file = tmp_path / "hidden.yaml"
    cfg_content = "hidden_repo_ids: [123, 456]\nhidden_repo_names: ['bad/actor', 'toxic/repo']\n"
    cfg_file.write_text(cfg_content)
    ids, names = site_data.load_hidden_repos(cfg_file)

    assert 123 in ids
    assert 456 in ids
    assert "bad/actor" in names

    assert site_data.is_repo_hidden(123, "normal/repo", ids, names) is True
    assert site_data.is_repo_hidden(999, "bad/actor", ids, names) is True
    assert site_data.is_repo_hidden(999, "Bad/Actor", ids, names) is True
    assert site_data.is_repo_hidden(999, "good/repo", ids, names) is False


def test_json_schemas_validation():
    # Test valid leaderboard item
    lb_data = [
        {
            "rank": 1,
            "repo_id": 1001,
            "repo_name": "owner/fast-lib",
            "html_url": "https://github.com/owner/fast-lib",
            "description": "A very fast library",
            "language": "Python",
            "age_days": 15,
            "stars_total_observed": 120,
            "stars_7d": 80,
            "spark_stars_28d": [0] * 28,
            "prob": 0.28,
            "prob_label": "~1 in 4",
            "explanation": "Flagged because 80 stars in 7 days.",
            "first_flagged_date": "2026-10-15",
            "days_on_board": 5,
            "rank_change": "up",
            "suspicion_score": None,
            "b1_rank": 2,
        }
    ]
    site_data.validate_json(lb_data, "leaderboard.schema.json")

    # Invalid leaderboard item (missing rank, bad sparkline length)
    bad_lb = [{"repo_id": 1001, "spark_stars_28d": [1, 2]}]
    with pytest.raises(jsonschema.ValidationError):
        site_data.validate_json(bad_lb, "leaderboard.schema.json")

    # Test valid track record
    tr_data = {
        "matured_snapshots": [],
        "summary": {
            "n_live_days": 10,
            "n_matured_days": 0,
            "top25_hit_rate": 0.0,
            "base_rate": 0.0051,
            "b1_hit_rate": 0.0286,
            "median_lead_time_days": 1.0,
        },
        "calibration": [
            {
                "bin_start": 0.0,
                "bin_end": 0.1,
                "predicted_avg": 0.05,
                "realized_avg": 0.05,
                "count": 10,
            }
        ],
        "ledger": {
            "first_date": "2026-10-10",
            "last_date": "2026-10-20",
            "total_rows": 10,
            "last_hash": "abc",
            "genesis_hash": "000",
            "verified": True,
        },
    }
    site_data.validate_json(tr_data, "track_record.schema.json")

    # Test valid meta
    meta_data = {
        "build_time": "2026-10-20T12:00:00+00:00",
        "model_version": "v1",
        "data_through": "2026-10-20",
        "counts": {
            "leaderboard": 50,
            "detail_pages": 50,
            "matured_snapshots": 0,
            "backtest_snapshots": 10,
        },
    }
    site_data.validate_json(meta_data, "meta.schema.json")


def test_explorer_parquet_size_limit():
    cfg = get_config()
    max_mb = cfg.site.explorer_max_mb
    assert site_data.OOF_TOP100_PARQUET.exists()
    size_mb = site_data.OOF_TOP100_PARQUET.stat().st_size / (1024 * 1024)
    assert size_mb <= max_mb, f"oof_top100.parquet ({size_mb:.2f} MB) exceeds budget ({max_mb} MB)"


def test_owner_fields_are_exported_and_validated():
    """Phase 14: leaderboard rows carry owner_id / owner_type for avatars (user vs organization)."""
    assert {"owner_type", "owner_id", "owner_login"} <= set(site_data.LIVE_META_KEYS)
    row = {
        "rank": 1,
        "repo_id": 1,
        "repo_name": "o/r",
        "html_url": "https://github.com/o/r",
        "description": None,
        "language": None,
        "age_days": 1,
        "stars_total_observed": 1,
        "stars_7d": 0,
        "spark_stars_28d": [0] * 28,
        "prob": 0.1,
        "prob_label": "~1 in 10",
        "explanation": None,
        "first_flagged_date": None,
        "days_on_board": 1,
        "rank_change": "new",
        "suspicion_score": None,
        "b1_rank": None,
    }
    site_data.validate_json(
        [{**row, "owner_id": 5, "owner_type": "Organization"}], "leaderboard.schema.json"
    )
    site_data.validate_json(
        [{**row, "owner_id": None, "owner_type": None}], "leaderboard.schema.json"
    )
    with pytest.raises(jsonschema.ValidationError):
        site_data.validate_json([{**row, "owner_type": "Robot"}], "leaderboard.schema.json")
