"""Tamper-evident daily prediction ledger (§9.2 Step 11, §9.6).

Maintains a SHA-256 chain of daily predictions in ``ledger/predictions.csv``:
``date,model_version,n_candidates,file_sha256,top50_repo_ids_sha256,hf_commit,prev_row_hash,row_hash``
where ``row_hash = sha256(prev_row_hash + "|" + all other fields)``.
"""

from __future__ import annotations

import csv
import hashlib
from datetime import date
from pathlib import Path

import duckdb

from breakout import paths as P
from breakout.config import Config
from breakout.logging import get_logger

log = get_logger(__name__)

LEDGER_PATH = P.ROOT / "ledger" / "predictions.csv"
GENESIS_HASH = "0" * 64
LEDGER_HEADER = [
    "date",
    "model_version",
    "n_candidates",
    "file_sha256",
    "top50_repo_ids_sha256",
    "hf_commit",
    "prev_row_hash",
    "row_hash",
]


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_top50_sha256(predictions_file: Path) -> str:
    """SHA-256 of the top-50 repo_ids (ordered by rank ascending)."""
    con = duckdb.connect()
    try:
        rows = con.execute(
            f"""
            select repo_id from read_parquet('{predictions_file}')
            order by rank asc, repo_id asc
            limit 50
            """
        ).fetchall()
        joined = ",".join(str(int(r[0])) for r in rows)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()
    finally:
        con.close()


def compute_row_hash(
    prev_hash: str,
    d: str,
    model_version: str,
    n_candidates: int,
    file_hash: str,
    top50_hash: str,
    hf_commit: str,
) -> str:
    payload = f"{prev_hash}|{d}|{model_version}|{n_candidates}|{file_hash}|{top50_hash}|{hf_commit}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_ledger(path: Path | None = None) -> list[dict[str, str]]:
    p = path or LEDGER_PATH
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def append_entry(
    date_val: date,
    model_version: str,
    n_candidates: int,
    predictions_file: Path,
    hf_commit: str = "",
    path: Path | None = None,
) -> tuple[str, bool]:
    """Append a prediction record to the ledger.

    Returns ``(row_hash, appended_bool)``. If an entry for ``date_val`` already exists with the
    same file_sha256, it is skipped (idempotent).
    """
    p = path or LEDGER_PATH
    p.parent.mkdir(parents=True, exist_ok=True)

    file_hash = file_sha256(predictions_file)
    top50_hash = compute_top50_sha256(predictions_file)
    date_str = date_val.isoformat()

    existing = read_ledger(p)
    if existing:
        for r in existing:
            if r["date"] == date_str and r["file_sha256"] == file_hash:
                log.info(
                    "Ledger entry for %s with hash %s already exists; skipping",
                    date_str,
                    file_hash,
                )
                return r["row_hash"], False
            if r["date"] == date_str and r["file_sha256"] != file_hash:
                log.warning(
                    "Ledger conflict for %s: existing hash %s != new hash %s",
                    date_str,
                    r["file_sha256"],
                    file_hash,
                )
        prev_hash = existing[-1]["row_hash"]
    else:
        prev_hash = GENESIS_HASH

    row_hash = compute_row_hash(
        prev_hash,
        date_str,
        model_version,
        n_candidates,
        file_hash,
        top50_hash,
        hf_commit,
    )

    write_header = not p.exists() or p.stat().st_size == 0
    with open(p, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_HEADER)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "date": date_str,
                "model_version": model_version,
                "n_candidates": str(n_candidates),
                "file_sha256": file_hash,
                "top50_repo_ids_sha256": top50_hash,
                "hf_commit": hf_commit,
                "prev_row_hash": prev_hash,
                "row_hash": row_hash,
            }
        )

    log.info("Appended ledger entry for %s: row_hash=%s", date_str, row_hash)
    return row_hash, True


def verify_ledger(
    cfg: Config | None = None,
    path: Path | None = None,
    remote: bool = False,
) -> tuple[bool, str]:
    """Verify integrity of the prediction ledger.

    Checks:
    1. Header correctness.
    2. SHA-256 hash chaining from GENESIS_HASH.
    3. If remote=True (or file is present locally), verifies snapshot file SHA-256 and top-50 hash.
    """
    p = path or LEDGER_PATH
    if not p.exists():
        return True, "Ledger does not exist yet (empty)."

    rows = read_ledger(p)
    if not rows:
        return True, "Ledger is empty."

    expected_prev = GENESIS_HASH
    for idx, r in enumerate(rows):
        d = r.get("date", "")
        if r.get("prev_row_hash") != expected_prev:
            prev_got = r.get("prev_row_hash")
            return (
                False,
                f"Row {idx + 1} ({d}): prev_row_hash {prev_got} != expected {expected_prev}",
            )

        calc_hash = compute_row_hash(
            r["prev_row_hash"],
            r["date"],
            r["model_version"],
            int(r["n_candidates"]),
            r["file_sha256"],
            r["top50_repo_ids_sha256"],
            r.get("hf_commit", ""),
        )
        if calc_hash != r.get("row_hash"):
            return (
                False,
                f"Row {idx + 1} ({d}): computed row_hash {calc_hash} != {r.get('row_hash')}",
            )

        # Check snapshot file if present locally
        local_cand = [
            P.DATA_DIR / "run" / f"predictions_{d}.parquet",
            P.DATA_DIR / "snapshots" / "predictions" / f"date={d}" / "predictions.parquet",
        ]
        found_file = next((f for f in local_cand if f.exists()), None)

        if remote and not found_file and cfg is not None:
            # Download from Hugging Face snapshots repo
            from breakout.lake import hf

            api = hf.get_api()
            rel = f"predictions/date={d}/predictions.parquet"
            dest = P.DATA_DIR / "snapshots" / "predictions" / f"date={d}"
            try:
                hf.download_files(api, cfg, "snapshots", [rel], dest)
                if (dest / "predictions.parquet").exists():
                    found_file = dest / "predictions.parquet"
            except Exception as e:
                log.warning("Could not download remote snapshot for %s: %s", d, e)

        if found_file:
            real_file_hash = file_sha256(found_file)
            if real_file_hash != r["file_sha256"]:
                return (
                    False,
                    f"Row {idx + 1} ({d}): file_sha256 {r['file_sha256']} != disk {real_file_hash}",
                )
            real_top50 = compute_top50_sha256(found_file)
            if real_top50 != r["top50_repo_ids_sha256"]:
                return (
                    False,
                    f"Row {idx + 1} ({d}): top50 {r['top50_repo_ids_sha256']} != disk {real_top50}",
                )

        expected_prev = r["row_hash"]

    return True, f"Verified {len(rows)} ledger entries successfully."
