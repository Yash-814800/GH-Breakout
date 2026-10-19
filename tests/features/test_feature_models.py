"""The Phase 7 dbt models on a tiny synthetic warehouse with hand-checkable expectations."""

from __future__ import annotations

import math
import os
import statistics

import duckdb
import pytest

from breakout import dbt_runner
from breakout import features_dict as fd
from breakout.config import get_config

from . import synth as S

MODELS = [
    "int_actor_early_stars",
    "int_actor_early_cum",
    "int_repo_first_hit",
    "int_tastemaker_thresholds",
    "feat_star_dynamics",
    "feat_activity",
    "feat_stargazers",
    "feat_tastemaker",
    "feat_owner",
    "feat_detail",
    "feat_enrich",
    "mart_repo_features",
]


@pytest.fixture(scope="module")
def wh(tmp_path_factory):
    path = tmp_path_factory.mktemp("synth") / "warehouse.duckdb"
    S.make(path)
    keys = ("GHB_WAREHOUSE", "GHB_DUCKDB_MEMORY", "DBT_TARGET_PATH", "DBT_LOG_PATH")
    old = {k: os.environ.get(k) for k in keys}
    os.environ["GHB_WAREHOUSE"] = str(path)
    os.environ["GHB_DUCKDB_MEMORY"] = "1000MB"
    os.environ["DBT_TARGET_PATH"] = str(
        path.parent / "target"
    )  # do not clobber a running build's target/
    os.environ["DBT_LOG_PATH"] = str(path.parent / "logs")
    try:
        cfg = get_config(None)
        rc = dbt_runner.run_dbt(
            cfg,
            ["run", "--select", *MODELS, "--full-refresh"],
            extra_vars={"n_buckets": 1},
        )
        assert rc == 0, "dbt run failed on the synthetic warehouse"
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return path


def row(wh, table: str, repo: int, d) -> dict:
    con = duckdb.connect(str(wh), read_only=True)
    try:
        cur = con.execute(
            f"select * from {table} where repo_id = ? and snapshot_date = ?", [repo, d]
        )
        cols = [c[0] for c in cur.description]
        r = cur.fetchall()
        assert len(r) == 1, f"{table}: {len(r)} rows for {repo} {d}"
        return dict(zip(cols, r[0], strict=True))
    finally:
        con.close()


def approx(a, b, tol=1e-9):
    assert a is not None and math.isclose(a, b, abs_tol=tol), (a, b)


def acts(off_lo: int, off_hi: int = -1):
    """ACT rows with offset in [off_lo, off_hi] as dicts."""
    keys = ["forks", "io", "ic", "ie", "ce", "pe", "po", "pm", "rv", "rl", "tg", "ps", "pu", "ac"]
    return [
        dict(zip(keys, v, strict=True), off=o, st=S.R_STARS.get(o, 0))
        for o, v in S.ACT.items()
        if off_lo <= o <= off_hi
    ]


def test_mart_has_one_row_per_candidate_and_matches_the_dictionary(wh):
    con = duckdb.connect(str(wh), read_only=True)
    n_c = con.execute("select count(*) from mart_candidates").fetchone()[0]
    n_m = con.execute(
        "select count(*), count(distinct (repo_id, snapshot_date)) from mart_repo_features"
    ).fetchone()
    cols = [r[0] for r in con.execute("describe mart_repo_features").fetchall()]
    con.close()
    assert n_m == (n_c, n_c)
    missing, extra = fd.compare_with_columns(fd.load(), cols)
    assert missing == [] and extra == [], (missing, extra)
    assert not [c for c in cols if c.startswith("_")]


def test_star_dynamics_windows_exclude_day_d_and_later(wh):
    f = row(wh, "feat_star_dynamics", S.R, S.D)
    st = {o: n for o, n in S.R_STARS.items() if o < 0}
    win = lambda n: sum(v for o, v in st.items() if o >= -n)  # noqa: E731
    assert (f["stars_1d"], f["stars_3d"], f["stars_7d"], f["stars_14d"], f["stars_28d"]) == (
        win(1),
        win(3),
        win(7),
        win(14),
        win(28),
    )
    assert f["stars_total_before"] == sum(st.values()) == 19
    prev = sum(v for o, v in st.items() if -14 <= o < -7)
    assert f["star_accel_7d"] == win(7) - prev
    approx(f["star_ratio_7d"], (win(7) + 1) / (prev + 1))
    assert f["days_since_first_star"] == 30
    assert f["star_active_days_14d"] == len([o for o in st if o >= -14])
    approx(f["star_max_day_share_14d"], max(v for o, v in st.items() if o >= -14) / win(14))
    # Gini over all 14 daily counts, zeros included, by the textbook formula
    x = sorted(st.get(o, 0) for o in range(-14, 0))
    g = 2 * sum((i + 1) * v for i, v in enumerate(x)) / (14 * sum(x)) - 15 / 14
    approx(f["star_gini_14d"], g)
    # hour share over [D-7, D): 3 stars in one hour
    approx(f["star_max_hour_share_7d"], 3 / win(7))
    assert f["_max_input_ts"] < __import__("datetime").datetime.combine(
        S.D, __import__("datetime").time()
    )


def test_activity_counts_and_sessions(wh):
    f = row(wh, "feat_activity", S.R, S.D)
    w14, w7 = acts(-14), acts(-7)
    assert f["forks_7d"] == sum(a["forks"] for a in w7) == 2
    assert f["forks_14d"] == sum(a["forks"] for a in w14) == 6
    stars14 = sum(a["st"] for a in w14)  # the stars of the ACTIVITY table (days that have a row)
    approx(f["fork_star_ratio_14d"], 6 / (stars14 + 1))
    assert f["actor_days_14d"] == sum(a["ac"] for a in w14)
    assert f["issue_events_14d"] == sum(a["ie"] for a in w14)
    assert f["comment_events_14d"] == sum(a["ce"] for a in w14) == 7
    assert f["pr_events_14d"] == 2 and f["reviews_14d"] == 3
    assert f["releases_total_before"] == 3 and f["days_since_last_release"] == 9
    assert f["push_active_days_14d"] == len([a for a in w14 if a["ps"] > 0]) == 4
    assert f["distinct_pushers_28d"] == 1  # actor 21; 22 is 29 days back, 23 pushed on D itself
    counts = [stars14, 6, sum(a["ie"] for a in w14), 7, 2, 3, sum(a["ps"] for a in w14)]
    tot = sum(counts)
    h = -sum(c / tot * math.log2(c / tot) for c in counts if c > 0)
    approx(f["event_type_entropy_14d"], h)
    # sessions: 6 started in the window; the straddling one and the one inside the gap are incomplete
    assert f["sessions_28d"] == 6
    assert f["distinct_contributors_28d"] == 4  # actors 11, 12, 13, 15 (14 started 29 days back)
    assert f["new_contributors_28d"] == 3  # 11, 12, 13 (15's first session was earlier)
    approx(f["first_time_contributor_rate_28d"], 3 / 4)
    approx(f["median_session_minutes_28d"], statistics.median([20, 60, 10, 5]))
    assert f["distinct_session_actors_28d"] == 3  # 11, 12, 15
    approx(f["top_actor_share_28d"], 6 / 11)  # actor 12 has 5 + 1 of 3 + 5 + 1 + 2 events


def test_stargazer_quality_and_retention_only_use_the_past(wh):
    f = row(wh, "feat_stargazers", S.R, S.D)
    assert f["sg_n"] == 5  # a41..a45; a46 starred on D-15, a47 on D
    approx(f["sg_share_experienced"], 2 / 5)
    assert f["sg_median_account_age_days"] == 100
    approx(f["sg_share_account_lt_30d"], 2 / 5)
    approx(f["sg_share_zero_prior_activity"], 1 / 5)
    assert f["sg_median_stars_same_day"] == 1
    approx(f["sg_share_bulk_starrers"], 1 / 5)
    # cohort = stars in [D-28, D-7): a51..a54 plus a45 (D-14) and a46 (D-15); a53's PR is after D and invisible
    approx(f["sg_retention_any_28d"], 3 / 6)
    approx(f["sg_retention_fork_28d"], 1 / 6)
    approx(f["sg_retention_issue_or_pr_28d"], 1 / 6)


def test_tastemaker_outcome_known_strictly_before_d(wh):
    tm = get_config(None).features.tastemaker
    k, p = tm.alpha, tm.beta
    f = row(wh, "feat_tastemaker", S.R, S.D)
    prior = k / (k + p)
    # stargazers in [D-14, D): a41..a45 plus a53 (D-10), a54 (D-8) and a55 (D-7) from the retention cohort
    scores = {
        41: (1 + k) / (2 + k + p),
        42: prior,
        43: (4 + k) / (5 + k + p),
        44: prior,
        45: prior,
        53: prior,
        54: prior,
        55: prior,
    }
    approx(f["sg_tm_mean_14d"], sum(scores.values()) / 8)
    approx(f["sg_tm_max_14d"], scores[43])
    assert (
        f["sg_tm_top_count_14d"] == 1
    )  # only a43 is in the top 1% of the 100 actors with >= 5 known stars
    approx(f["sg_tm_known_share_14d"], 2 / 8)
    # a41's hit on Z becomes known on D_B + 1: at D_B (outcome_day == D_B) it is NOT yet known
    b = row(wh, "feat_tastemaker", S.RB, S.D_B)
    c = row(wh, "feat_tastemaker", S.RB, S.D_C)
    approx(b["sg_tm_mean_14d"], (1 + k) / (2 + k + p))  # X (hit) and Y (miss)
    approx(c["sg_tm_mean_14d"], (2 + k) / (3 + k + p))  # + Z (hit)
    con = duckdb.connect(str(wh), read_only=True)
    cum = con.execute(
        "select outcome_day, early_stars_known, hits_known from int_actor_early_cum where actor_id = 41 order by 1"
    ).fetchall()
    con.close()
    assert [(n, h) for _, n, h in cum[:3]] == [(1, 1), (2, 1), (3, 2)]
    assert cum[2][0] == S.D_B  # Z's outcome day


def test_tastemaker_hit_definition(wh):
    con = duckdb.connect(str(wh), read_only=True)
    hits = dict(
        con.execute(
            "select repo_id, bool_or(is_hit) from int_actor_early_stars group by 1"
        ).fetchall()
    )
    con.close()
    assert hits[S.X] and hits[S.Z] and not hits[S.Y]
    assert all(hits[r] for r in S.H_REPOS) and not any(hits[r] for r in S.N_REPOS)


def test_owner_features_use_names_and_hits_known_before_d(wh):
    f = row(wh, "feat_owner", S.R, S.D)
    # same owner prefix (case-insensitive), first seen before D: 1500, 1501, 1503 (1502 appears after D)
    assert f["owner_prior_repos_seen"] == 3
    assert f["owner_prior_breakouts"] == 1  # 1500; 1503's hit is only known 10 days after D
    # a candidate whose owner has no other repos: 0, not NULL
    assert row(wh, "feat_owner", S.R0, S.D0)["owner_prior_repos_seen"] == 0


def test_detail_features_are_null_before_the_detail_era_and_zero_inside_it(wh):
    pre = row(wh, "feat_detail", S.R0, S.D0)
    nulls = [
        c
        for c in pre
        if c
        not in (
            "bucket",
            "repo_id",
            "snapshot_date",
            "era_post_2025_10",
            "detail_coverage_28d",
            "_max_input_ts",
        )
    ]
    assert all(pre[c] is None for c in nulls), {c: pre[c] for c in nulls if pre[c] is not None}
    assert pre["detail_coverage_28d"] == 0 and pre["era_post_2025_10"] == 0
    part = row(wh, "feat_detail", S.RP, S.DP)
    approx(part["detail_coverage_28d"], 4 / 28)  # 2023-06-01..04
    assert (
        part["issues_opened_28d"] == 0 and part["prs_opened_28d"] == 0
    )  # covered but quiet: 0, never NULL
    assert part["median_first_response_hours_28d"] is None  # no data is NULL, not 0
    f = row(wh, "feat_detail", S.R, S.D)
    assert f["detail_coverage_28d"] == 1
    w28 = acts(-28)
    assert f["issues_opened_28d"] == sum(a["io"] for a in w28) == 4
    assert f["issues_closed_28d"] == 1
    approx(f["issue_close_ratio_28d"], 1 / 4)
    assert f["prs_opened_28d"] == 3 and f["prs_merged_28d"] == 2
    assert f["tags_created_total_before"] == 3  # D+1's 5 tags are invisible
    # first responses: #1 after 2 h, #2 after 50 h; #3's reply comes after D and is excluded
    approx(f["median_first_response_hours_28d"], 26.0)
    approx(
        f["share_issues_responded_48h"], 1 / 3
    )  # #1 yes, #2 no (50 h), #4 never; #3 is newer than D-2
    approx(f["median_merge_hours_28d"], statistics.median([10, 24]))  # #2 merges after D
    assert f["core_actor_count_90d"] == 3  # 21, 22, 24; 25 is 100 days back, 23 acted on D
    assert f["external_pr_authors_28d"] == 2  # 31, 32; author 21 is a core actor


def test_enrichment_fields(wh):
    f = row(wh, "feat_enrich", S.R, S.D)
    assert (f["primary_language"], f["owner_type"]) == ("Python", "Organization")
    assert f["birth_from_public_event"] == 1 and f["days_api_created_to_birth"] == 5
    assert (f["hn_stories_before_14d"], f["hn_stories_before_3d"]) == (2, 1)
    assert (
        f["hn_max_points_aged"] == 400
    )  # the 50-point story is younger than 3 days, the 900-point one is 40 days old
    assert f["hn_any_before"] == 1
    assert row(wh, "feat_enrich", S.R3, S.D)["primary_language"] == "Other"
    assert row(wh, "feat_enrich", S.R4, S.D)["primary_language"] == "Unknown"
    nf = row(wh, "feat_enrich", S.RB, S.D_B)
    assert nf["owner_type"] == "Unknown" and nf["days_api_created_to_birth"] is None
    assert nf["hn_any_before"] == 0 and nf["hn_max_points_aged"] is None


def test_no_group_reads_a_timestamp_at_or_after_d(wh):
    con = duckdb.connect(str(wh), read_only=True)
    for g in ("star_dynamics", "activity", "stargazers", "tastemaker", "owner", "detail", "enrich"):
        n = con.execute(
            f"select count(*) from feat_{g} where _max_input_ts >= snapshot_date"
        ).fetchone()[0]
        assert n == 0, g
    con.close()


def test_leak_test_passes_on_the_synthetic_world(wh, tmp_path, monkeypatch):
    from breakout.features import leak

    monkeypatch.setenv("DBT_TARGET_PATH", str(tmp_path / "t"))
    monkeypatch.setenv("DBT_LOG_PATH", str(tmp_path / "l"))
    res = leak.run_leak_test(get_config(None), S.D, sample=10, warehouse=wh, workdir=tmp_path)
    assert res.passed, res.differences
    assert res.rows_compared == 3 and res.columns_compared == len(fd.load())
    # the copy of the full world reproduces the original mart exactly
    assert res.history_rows_compared == 3 and res.history_differences == 0


def test_compare_features_detects_a_difference(tmp_path):
    from breakout.features import leak

    paths = []
    for i, v in enumerate((1.0, 1.0 + 1e-3)):
        p = tmp_path / f"m{i}.duckdb"
        con = duckdb.connect(str(p))
        con.execute(
            "create table mart_repo_features (bucket smallint, repo_id bigint, snapshot_date date, a double, b integer)"
        )
        con.execute("insert into mart_repo_features values (1, 1, date '2024-01-01', ?, 5)", [v])
        con.close()
        paths.append(p)
    rows, ncols, diffs = leak.compare_features(paths[0], paths[1])
    assert (rows, ncols) == (1, 2) and [d["column"] for d in diffs] == ["a"]
    assert leak.compare_features(paths[0], paths[0])[2] == []
    # within the 1e-9 tolerance is equal
    con = duckdb.connect(str(paths[1]))
    con.execute("update mart_repo_features set a = 1.0 + 1e-12")
    con.close()
    assert leak.compare_features(paths[0], paths[1])[2] == []
