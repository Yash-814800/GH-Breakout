from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from breakout.config import get_config
from breakout.features import state


def test_state_dir_creation(tmp_path: Path, monkeypatch) -> None:
    s_dir = tmp_path / "derived" / "state"
    monkeypatch.setattr(state, "STATE_DIR", s_dir)
    assert not s_dir.exists()
    created = state.state_dir()
    assert created.exists()
    assert created == s_dir


def test_incremental_state_update(tmp_path: Path, monkeypatch) -> None:
    s_dir = tmp_path / "derived" / "state"
    s_dir.mkdir(parents=True, exist_ok=True)
    tm_path = s_dir / "tastemaker_state.parquet"
    own_path = s_dir / "owner_state.parquet"
    thresh_path = s_dir / "tastemaker_thresholds.parquet"

    monkeypatch.setattr(state, "STATE_DIR", s_dir)
    monkeypatch.setattr(state, "TASTEMAKER_STATE_PATH", tm_path)
    monkeypatch.setattr(state, "OWNER_STATE_PATH", own_path)
    monkeypatch.setattr(state, "TASTEMAKER_THRESHOLDS_PATH", thresh_path)

    # Initial state as of 2024-06-01
    as_of_0 = date(2024, 6, 1)
    tm_init = [
        {"actor_id": 1, "early_stars_known": 10, "hits_known": 2, "as_of": as_of_0},
        {"actor_id": 2, "early_stars_known": 5, "hits_known": 1, "as_of": as_of_0},
    ]
    pq.write_table(pa.Table.from_pylist(tm_init), tm_path)

    own_init = [
        {"owner": "alice", "prior_repos_seen": 3, "prior_breakouts": 1, "as_of": as_of_0},
        {"owner": "bob", "prior_repos_seen": 1, "prior_breakouts": 0, "as_of": as_of_0},
    ]
    pq.write_table(pa.Table.from_pylist(own_init), own_path)

    thresh_init = [
        {"month": date(2024, 6, 1), "score_threshold": 0.08, "n_actors": 100},
    ]
    pq.write_table(pa.Table.from_pylist(thresh_init), thresh_path)

    # Create synthetic warehouse connection with intermediate tables
    con = duckdb.connect()
    con.execute(
        """
        create table int_actor_early_stars (
            actor_id bigint,
            is_hit boolean,
            outcome_day date
        );
        insert into int_actor_early_stars values
            (1, true, date '2024-06-05'),
            (1, false, date '2024-06-07'),
            (3, true, date '2024-06-08');

        create table stg_repo_name_history (
            repo_id bigint,
            repo_name varchar,
            first_seen date
        );
        insert into stg_repo_name_history values
            (100, 'alice/repo-new', date '2024-06-04'),
            (200, 'charlie/new-repo', date '2024-06-06');

        create table int_repo_first_hit (
            repo_id bigint,
            first_hit_outcome_day date
        );
        insert into int_repo_first_hit values
            (100, date '2024-06-05');
        """
    )

    cfg = get_config(None)
    # Update state to 2024-06-10
    target_d = date(2024, 6, 10)
    state.update_state(cfg, target_d, con=con, upload=False)

    # Verify updated tastemaker state
    tm_updated = pq.read_table(tm_path).to_pylist()
    tm_map = {r["actor_id"]: r for r in tm_updated}
    assert tm_map[1]["early_stars_known"] == 12  # 10 + 2 new
    assert tm_map[1]["hits_known"] == 3  # 2 + 1 new hit
    assert tm_map[1]["as_of"] == target_d
    assert tm_map[2]["early_stars_known"] == 5  # unchanged
    assert tm_map[3]["early_stars_known"] == 1  # newly seen actor
    assert tm_map[3]["hits_known"] == 1

    # Verify updated owner state
    own_updated = pq.read_table(own_path).to_pylist()
    own_map = {r["owner"]: r for r in own_updated}
    assert own_map["alice"]["prior_repos_seen"] == 4  # 3 + 1
    assert own_map["alice"]["prior_breakouts"] == 2  # 1 + 1
    assert own_map["charlie"]["prior_repos_seen"] == 1
