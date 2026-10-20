from __future__ import annotations

from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from breakout.ops import ledger


def _make_dummy_predictions(path: Path, n: int = 60) -> Path:
    rows = []
    for i in range(1, n + 1):
        rows.append(
            {
                "snapshot_date": "2024-06-03",
                "repo_id": 1000 + i,
                "repo_name": f"owner/repo_{i}",
                "rank": i,
                "prob": 0.5 - (i * 0.005),
                "raw_score": 1.0 - (i * 0.01),
                "b1_rank": i + 1,
                "explanation": "Flagged because test",
                "top_contribs": "{}",
                "model_version": "v1.0",
                "features_hash": "abc",
                "schema_version": 1,
                "suspicion_score": None,
            }
        )
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)
    return path


def test_empty_ledger_verification(tmp_path: Path) -> None:
    p = tmp_path / "ledger.csv"
    ok, msg = ledger.verify_ledger(path=p)
    assert ok
    assert "empty" in msg.lower() or "not exist" in msg.lower()


def test_ledger_append_and_hash_chain(tmp_path: Path) -> None:
    ledger_file = tmp_path / "predictions.csv"
    pred1 = _make_dummy_predictions(tmp_path / "pred1.parquet", n=60)
    pred2 = _make_dummy_predictions(tmp_path / "pred2.parquet", n=70)

    # Day 1
    h1, appended1 = ledger.append_entry(
        date_val=date(2024, 6, 3),
        model_version="v1.0",
        n_candidates=60,
        predictions_file=pred1,
        hf_commit="commit1",
        path=ledger_file,
    )
    assert appended1
    assert len(h1) == 64

    # Idempotent repeat
    h1_repeat, appended_repeat = ledger.append_entry(
        date_val=date(2024, 6, 3),
        model_version="v1.0",
        n_candidates=60,
        predictions_file=pred1,
        hf_commit="commit1",
        path=ledger_file,
    )
    assert not appended_repeat
    assert h1_repeat == h1

    # Day 2
    h2, appended2 = ledger.append_entry(
        date_val=date(2024, 6, 4),
        model_version="v1.0",
        n_candidates=70,
        predictions_file=pred2,
        hf_commit="commit2",
        path=ledger_file,
    )
    assert appended2
    assert len(h2) == 64
    assert h2 != h1

    # Verify rows in CSV
    rows = ledger.read_ledger(ledger_file)
    assert len(rows) == 2
    assert rows[0]["prev_row_hash"] == ledger.GENESIS_HASH
    assert rows[0]["row_hash"] == h1
    assert rows[1]["prev_row_hash"] == h1
    assert rows[1]["row_hash"] == h2

    # Verification passes
    ok, msg = ledger.verify_ledger(path=ledger_file)
    assert ok, msg
    assert "Verified 2 ledger entries" in msg


def test_ledger_tamper_detection(tmp_path: Path) -> None:
    ledger_file = tmp_path / "predictions.csv"
    pred1 = _make_dummy_predictions(tmp_path / "pred1.parquet", n=60)

    h1, _ = ledger.append_entry(
        date_val=date(2024, 6, 3),
        model_version="v1.0",
        n_candidates=60,
        predictions_file=pred1,
        hf_commit="commit1",
        path=ledger_file,
    )

    # Tamper with row_hash
    lines = ledger_file.read_text().splitlines()
    header = lines[0]
    tampered_row = lines[1].replace(h1, "f" * 64)
    ledger_file.write_text(f"{header}\n{tampered_row}\n")

    ok, msg = ledger.verify_ledger(path=ledger_file)
    assert not ok
    assert "row_hash" in msg
