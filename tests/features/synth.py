"""A tiny synthetic warehouse with the upstream tables the Phase 7 models read (Phase 7 tests).

Everything is placed relative to the snapshot day ``D`` so the expectations in the tests are easy to read:
``day(-3)`` is D - 3 days. The helpers only create the tables; the tests assert on hand-computed values.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

D = date(2024, 3, 4)  # a Monday after detail_start_date (2023-06-01)
D_B = D + timedelta(days=30)  # tastemaker boundary: Z's outcome_day == D_B (not known)
D_C = D + timedelta(days=31)  # ... and one day later (known)
D0 = date(2023, 3, 6)  # before detail_start_date
DP = date(2023, 6, 5)  # 5 days after detail_start_date

R, RB, R0, RP, R3, R4 = 1000, 1100, 1300, 1400, 1200, 1250  # candidate repos
X, Y, Z = 2000, 2001, 2002  # a41's earlier early-star repos: hit known, miss known, hit unknown
Q = 2003  # a42's early star on day(-60): its 60-day outcome day is exactly D (not yet known at D)
OWN_HIT, OWN_SEEN, OWN_LATE, OWN_HITLATE, OWN_OTHER = 1500, 1501, 1502, 1503, 1504
H_REPOS = [3000, 3001, 3002, 3003]  # repos that gain 600 stars on day(-60)
N_REPOS = [3010, 3011, 3012, 3013, 3014]  # repos that never gain


def day(n: int, base: date = D) -> date:
    return base + timedelta(days=n)


def ts(n: float, base: date = D) -> datetime:
    """Timestamp n days (fractions allowed) from midnight of ``base``."""
    return datetime.combine(base, datetime.min.time()) + timedelta(days=n)


DDL = {
    "mart_candidates": "bucket smallint, repo_id bigint, snapshot_date date, birth_at timestamp, age_days bigint,"
    " stars_total_before integer, stars_1d integer, stars_7d integer, stars_14d integer, stars_prev_7d integer,"
    " birth_source varchar, repo_name_at_D varchar",
    "int_repo_star_daily": "bucket smallint, repo_id bigint, day date, n_stars integer",
    "int_repo_birth": "repo_id bigint, birth_at timestamp",
    "int_early_stars": "repo_id bigint, actor_id bigint, starred_at timestamp, star_day date, event_id bigint",
    "stg_stars": "bucket smallint, repo_id bigint, actor_id bigint, starred_at timestamp, event_id bigint,"
    " detail_level utinyint",
    "int_star_events_enriched": "bucket smallint, repo_id bigint, actor_id bigint, starred_at timestamp, star_day date,"
    " est_account_created_at timestamp, est_is_extrapolated boolean, account_age_days_at_star integer,"
    " actor_events_prior_90d bigint, actor_repos_prior_90d bigint, actor_stars_prior_90d bigint,"
    " actor_stars_same_day integer",
    "int_stargazer_later_actions": "bucket smallint, repo_id bigint, actor_id bigint, starred_at timestamp,"
    " action_type varchar, action_at timestamp, action_event_id bigint, days_after_star integer",
    "int_repo_daily_activity": "bucket smallint, repo_id bigint, day date, n_stars integer, n_forks integer,"
    " n_issues_opened integer, n_issues_closed integer, n_issue_events integer, n_comment_events integer,"
    " n_pr_events integer, n_issue_comments integer, n_pr_comments integer, n_prs_opened integer,"
    " n_prs_closed integer, n_prs_merged integer, n_reviews integer, n_releases integer,"
    " n_creates_branch integer, n_creates_tag integer, n_pushes integer, n_pushers integer,"
    " n_distinct_actors integer, detail_level_min tinyint",
    "int_core_actors_daily": "repo_id bigint, actor_id bigint, day date, pushed boolean, closed_pr boolean,"
    " is_owner boolean",
    "int_contributor_sessions": "bucket smallint, repo_id bigint, actor_id bigint, session_id integer,"
    " session_start timestamp, session_end timestamp, n_events integer, event_types varchar[]",
    "int_issue_response": "repo_id bigint, number integer, opened_at timestamp, author_id bigint,"
    " first_response_at timestamp, closed_at timestamp",
    "int_pr_lifecycle": "repo_id bigint, number integer, opened_at timestamp, author_id bigint,"
    " closed_at timestamp, merged_at timestamp, first_review_at timestamp",
    "stg_repo_name_history": "repo_id bigint, repo_name varchar, first_seen timestamp, last_seen timestamp,"
    " n_events bigint",
    "stg_repo_metadata": "repo_id bigint, status varchar, fetched_at timestamp, api_created_at timestamp,"
    " is_fork boolean, parent_repo_id bigint, is_archived boolean, is_mirror boolean, is_template boolean,"
    " primary_language varchar, owner_type varchar, owner_id bigint, owner_created_at timestamp",
    "stg_hn_stories": "story_id bigint, created_at timestamp, points integer, num_comments integer,"
    " repo_id bigint, repo_name varchar, fetched_at timestamp",
    "top_languages": "language varchar",
}

# daily star counts of R: day offset -> stars. Offsets 0 and +1 are in the future of D and must be ignored.
R_STARS = {-30: 1, -15: 5, -14: 2, -8: 3, -7: 1, -5: 1, -2: 2, -1: 4, 0: 7, 1: 9}
# stars of R by hour for the day(-1) burst: 3 stars in hour 10, 1 in hour 11
R_STAR_TIMES = (
    [ts(-30 + 0.5)]
    + [ts(-15 + 0.5)] * 5
    + [ts(-14 + 0.1), ts(-14 + 0.2)]
    + [ts(-8 + 0.1), ts(-8 + 0.2), ts(-8 + 0.3)]
    + [ts(-7 + 0.1)]
    + [ts(-5 + 0.1)]
    + [ts(-2 + 1 / 24), ts(-2 + 2 / 24)]
    + [
        ts(-1 + 10 / 24 + 1 / 1440),
        ts(-1 + 10 / 24 + 2 / 1440),
        ts(-1 + 10 / 24 + 3 / 1440),
        ts(-1 + 11 / 24),
    ]
    + [ts(0.2)] * 7
    + [ts(1.2)] * 9
)


# daily activity of R: offset -> (forks, issues opened, issues closed, issue events, comment events, PR events,
# PRs opened, PRs merged, reviews, releases, tags, pushes, pushers, distinct actors)
ACT = {
    -100: (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    -60: (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0),
    -50: (0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0),
    -20: (0, 1, 0, 5, 0, 0, 1, 0, 0, 0, 0, 9, 1, 2),
    -19: (0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1),
    -16: (0, 0, 0, 0, 9, 0, 0, 0, 0, 0, 0, 0, 0, 1),
    -15: (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 1),
    -13: (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 1, 4),
    -12: (0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1),
    -10: (4, 1, 0, 2, 0, 0, 1, 0, 0, 0, 0, 0, 0, 2),
    -9: (0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 1, 1, 1),
    -5: (0, 0, 0, 0, 0, 2, 1, 0, 3, 0, 0, 0, 0, 2),
    -4: (0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1),
    -3: (2, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1),
    -2: (0, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0, 2, 1, 2),
    -1: (0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 5, 1, 3),
    0: (100, 5, 0, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9),  # day D itself and later: invisible
    1: (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 0, 0),
    3: (0, 0, 0, 0, 0, 0, 0, 0, 0, 4, 0, 0, 0, 0),
}


def make(path: Path) -> None:
    """Create and fill the synthetic warehouse at ``path``."""
    con = duckdb.connect(str(path))
    for name, cols in DDL.items():
        con.execute(f"create table {name} ({cols})")

    def ins(table: str, rows: list[tuple[Any, ...]]) -> None:
        if rows:
            n = len(rows[0])
            con.executemany(f"insert into {table} values ({','.join('?' * n)})", rows)

    # ---- candidates -------------------------------------------------------------------------------
    cand = lambda rid, d, name, birth_off=-40, src="create_event": (  # noqa: E731
        rid % 32,
        rid,
        d,
        ts(birth_off, d),
        40,
        19,
        4,
        8,
        13,
        5,
        src,
        name,
    )
    ins(
        "mart_candidates",
        [
            cand(R, D, "acme/proj", src="public_event"),
            cand(R3, D, "lang/other"),
            cand(R4, D, "lang/none"),
            cand(RB, D_B, "tm/b"),
            cand(RB, D_C, "tm/b"),
            cand(R0, D0, "old/repo"),
            cand(RP, DP, "new/repo"),
        ],
    )
    con.execute("update mart_candidates set bucket = repo_id % 32")
    # ---- star days / stars of R ----------------------------------------------------------------------
    ins("int_repo_star_daily", [(R % 32, R, day(o), n) for o, n in R_STARS.items()])
    ins("stg_stars", [(R % 32, R, 900 + i, t, i, 1) for i, t in enumerate(R_STAR_TIMES)])
    ins("int_repo_birth", [(rid, ts(-40)) for rid in (R, R3, R4)])
    # ---- stargazers of R in [D-14, D) (a41..a45), D-15 and D (ignored) ------------------------------------
    # actor, star offset, events90, repos90, age days, stars same day
    sg = [
        (41, -1, 20, 3, 400, 1),
        (42, -2, 0, 0, 5, 1),
        (43, -3, 12, 1, 100, 60),
        (44, -5, 50, 5, 1000, 2),
        (45, -14, 3, 1, 20, 1),
        (46, -15, 99, 9, 999, 1),
        (47, 0, 99, 9, 999, 1),
    ]
    ins(
        "int_star_events_enriched",
        [
            (R % 32, R, a, ts(o + 0.3), day(o), ts(o - age), False, age, ev, rp, 0, same)
            for a, o, ev, rp, age, same in sg
        ],
    )
    es = [(R, a, ts(o + 0.3), day(o), 5000 + a) for a, o, *_ in sg]
    # retention cohort: stars in [D-28, D-7): a51..a54 ; D-7 (a55) and D-29 (a56) are outside
    coh = [(51, -20), (52, -15), (53, -10), (54, -8), (55, -7), (56, -29)]
    es += [(R, a, ts(o + 0.4), day(o), 5100 + a) for a, o in coh]
    ins(
        "int_stargazer_later_actions",
        [
            (R % 32, R, 51, ts(-20 + 0.4), "fork", ts(-5), 1, 15),
            (R % 32, R, 51, ts(-20 + 0.4), "comment", ts(-2), 2, 18),
            (R % 32, R, 52, ts(-15 + 0.4), "issue", ts(-12), 3, 3),
            (R % 32, R, 53, ts(-10 + 0.4), "pull_request", ts(1), 4, 11),  # after D: invisible
            (R % 32, R, 54, ts(-8 + 0.4), "comment", ts(-1), 5, 7),
        ],
    )
    # ---- tastemaker world ------------------------------------------------------------------------------
    births = {Q: -70, X: -150, Y: -120, Z: -100, OWN_HIT: -210, OWN_HITLATE: -60, RB: -40}
    births.update({h: -110 for h in H_REPOS + N_REPOS})
    ins("int_repo_birth", [(rid, ts(b)) for rid, b in births.items()])
    star_day_rows: dict[tuple[int, int], int] = {}
    eid = [10_000]

    def early(rid: int, actor: int, off: int) -> None:
        es.append((rid, actor, ts(off + 0.5), day(off), eid[0]))
        star_day_rows[(rid, off)] = star_day_rows.get((rid, off), 0) + 1
        eid[0] += 1

    early(X, 41, -100)
    early(Y, 41, -90)
    early(Z, 41, -30)
    early(OWN_HIT, 70, -200)
    early(OWN_HITLATE, 71, -50)
    early(RB, 41, 29)  # a41 stars RB the day before D_B / D_C
    early(Q, 42, -60)  # outcome_day == D: must NOT count at D (strict), would at D + 1
    # 100 eligible actors with 5 known early stars each: 97 have 0 hits, two 3 hits, a43 has 4 hits
    plan = {43: 4, 80: 3, 81: 3}
    for a in range(82, 82 + 97):
        plan[a] = 0
    for a, hits in plan.items():
        for r in H_REPOS[:hits] + N_REPOS[: 5 - hits]:
            early(r, a, -100)
    ins("int_early_stars", es)
    # star-day rows of the early-star repos: their own first stars plus the 600-star jumps
    sd = [(rid % 32, rid, day(off), n) for (rid, off), n in star_day_rows.items()]
    sd += [(rid % 32, rid, day(-60), 600) for rid in H_REPOS]
    sd += [
        (Q % 32, Q, day(-30), 600),
        (X % 32, X, day(-90), 600),
        (Z % 32, Z, day(-10), 700),
        (OWN_HIT % 32, OWN_HIT, day(-190), 600),
        (OWN_HITLATE % 32, OWN_HITLATE, day(-40), 600),
    ]
    ins("int_repo_star_daily", sd)
    # ---- activity of R ---------------------------------------------------------------------------------------
    # offset: (forks, iss_open, iss_close, iss_ev, comm_ev, pr_ev, prs_open, prs_merged, reviews, releases,
    #          tags, pushes, pushers, actors)
    rows = []
    for off, (fk, io, ic, ie, ce, pe, po, pm, rv, rl, tg, ps, pu, ac) in ACT.items():
        stars = R_STARS.get(off, 0)
        rows.append(
            (
                R % 32,
                R,
                day(off),
                stars,
                fk,
                io,
                ic,
                ie,
                ce,
                pe,
                0,
                0,
                po,
                0,
                pm,
                rv,
                rl,
                0,
                tg,
                ps,
                pu,
                ac,
                1,
            )
        )
    ins("int_repo_daily_activity", rows)
    # pushers / maintainers
    ins(
        "int_core_actors_daily",
        [
            (R, 21, day(-3), True, False, False),
            (R, 21, day(-10), True, False, False),
            (R, 22, day(-29), True, False, False),
            (R, 23, day(0), True, False, False),
            (R, 24, day(-60), False, True, False),
            (R, 25, day(-100), False, False, True),
        ],
    )
    # sessions
    ev = ["issue_comment"]
    ins(
        "int_contributor_sessions",
        [
            (R % 32, R, 11, 1, ts(-10 + 10 / 24), ts(-10 + 10 / 24 + 20 / 1440), 3, ev),
            (R % 32, R, 12, 1, ts(-5 + 10 / 24), ts(-5 + 10 / 24 + 60 / 1440), 5, ev),
            (R % 32, R, 12, 2, ts(-3 + 10 / 24), ts(-3 + 10 / 24 + 10 / 1440), 1, ev),
            (
                R % 32,
                R,
                11,
                2,
                ts(-1 + 23 / 24 + 50 / 1440),
                ts(0 + 10 / 1440),
                4,
                ev,
            ),  # straddles D
            (
                R % 32,
                R,
                13,
                1,
                ts(-1 + 23 / 24 + 40 / 1440),
                ts(-1 + 23 / 24 + 45 / 1440),
                2,
                ev,
            ),  # within the gap of D
            (R % 32, R, 14, 1, ts(-29), ts(-29 + 5 / 1440), 2, ev),  # before the window
            (R % 32, R, 15, 2, ts(-20), ts(-20 + 5 / 1440), 2, ev),  # second session only
        ],
    )
    # issues and PRs
    ins(
        "int_issue_response",
        [
            (R, 1, ts(-20 + 10 / 24), 31, ts(-20 + 12 / 24), ts(-19)),
            (R, 2, ts(-10 + 10 / 24), 32, ts(-10 + 10 / 24 + 50 / 24), None),
            (R, 3, ts(-1 + 10 / 24), 33, ts(1), None),  # response after D
            (R, 4, ts(-3), 34, None, None),
        ],
    )
    ins(
        "int_pr_lifecycle",
        [
            (R, 1, ts(-20), 31, ts(-19), ts(-20 + 10 / 24), None),
            (R, 2, ts(-10), 32, ts(2), ts(2), None),  # merged after D
            (R, 3, ts(-5), 21, ts(-4), ts(-5 + 1), None),
        ],
    )
    # ---- owner, metadata, HN --------------------------------------------------------------------------------
    nh = lambda rid, name, off: (rid, name, ts(off), ts(off), 1)  # noqa: E731
    ins(
        "stg_repo_name_history",
        [
            nh(R, "acme/proj", -100),
            nh(OWN_HIT, "acme/other1", -200),
            nh(OWN_SEEN, "ACME/other2", -5),
            nh(OWN_LATE, "acme/late", 3),
            nh(OWN_HITLATE, "acme/hit-late", -50),
            nh(OWN_OTHER, "other/x", -300),
            nh(R3, "lang/other", -50),
            nh(R4, "lang/none", -50),
            nh(RB, "tm/b", 5),
        ],
    )
    meta = lambda rid, status, lang, owner, api_off: (  # noqa: E731
        rid,
        status,
        ts(0),
        ts(api_off) if api_off is not None else None,
        False,
        None,
        False,
        False,
        False,
        lang,
        owner,
        1,
        None,
    )
    ins(
        "stg_repo_metadata",
        [
            meta(R, "ok", "Python", "Organization", -45),
            meta(R3, "ok", "Brainfuck", "User", -41),
            meta(R4, "ok", None, "User", -41),
            meta(RB, "not_found", None, None, None),
        ],
    )
    ins(
        "stg_hn_stories",
        [
            (1, ts(-2), 50, 5, R, "acme/proj", ts(5)),
            (2, ts(-10), 400, 50, R, "acme/proj", ts(5)),
            (3, ts(-20), 100, 9, R, "acme/proj", ts(5)),
            (4, ts(-40), 900, 90, R, "acme/proj", ts(5)),
            (5, ts(1), 999, 99, R, "acme/proj", ts(5)),
        ],
    )
    ins("top_languages", [("Python",), ("Go",)])
    con.close()
