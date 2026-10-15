from __future__ import annotations

from datetime import date

import pyarrow.parquet as pq

from breakout.lake import catalog as cat
from breakout.lake import compact, hf, layout, sync
from breakout.lake.verify import verify_lake, verify_remote

JUNE = (date(2023, 6, 1), date(2023, 7, 1))


def _june_days(lake, days=range(1, 31)):
    for d in days:
        lake.day(date(2023, 6, d), n=4)
    lake.manifest(*JUNE, ok_days={date(2023, 6, d) for d in days})


def test_push_files_adds_catalog_and_skips_unchanged(cfg, api, lake):
    lake.bq("WatchEvent", 2022, 1)
    lake.bq("ForkEvent", 2022, 1)
    files = cat.lake_files(lake.root)
    commits = sync.push_files(api, cfg, lake.root, files, "push")
    assert len(commits) == 1
    repo = api.repos["u/events"]
    assert hf.CATALOG_PATH in repo
    remote, _ = sync.fetch_remote_catalog(api, cfg)
    assert sorted(remote.column("path").to_pylist()) == sorted(
        f.relative_to(lake.root).as_posix() for f in files
    )
    assert sync.push_files(api, cfg, lake.root, files, "again") == []  # idempotent
    assert len(api.commits) == 1


def test_every_commit_carries_a_consistent_catalog(cfg, api, lake):
    for m in (1, 2, 3):
        lake.bq("WatchEvent", 2022, m)
        lake.bq("ForkEvent", 2022, m)
    files = cat.lake_files(lake.root)
    sync.push_files(api, cfg, lake.root, files, "push")  # 6 files, 3 per commit
    assert len(api.commits) == 2
    assert all(hf.CATALOG_PATH in c["adds"] for c in api.commits)


def test_concurrent_catalog_update_is_retried(cfg, api, lake):
    lake.bq("WatchEvent", 2022, 1)
    files = cat.lake_files(lake.root)
    real = api.create_commit
    state = {"raced": False}

    def racing(*a, **kw):
        if not state["raced"]:
            state["raced"] = True
            api.heads["u/events"] += 1  # someone else committed in between
        return real(*a, **kw)

    api.create_commit = racing  # type: ignore[method-assign]
    commits = sync.push_files(api, cfg, lake.root, files, "push")
    assert len(commits) == 1 and state["raced"]


def test_pull_downloads_only_selected_files(cfg, api, lake, tmp_path):
    for m in (1, 2, 3):
        lake.bq("WatchEvent", 2022, m)
        lake.bq("ForkEvent", 2022, m)
    sync.push_files(api, cfg, lake.root, cat.lake_files(lake.root), "push")
    api.downloads.clear()
    dest = tmp_path / "pulled"
    got = sync.pull(
        api,
        cfg,
        types=["WatchEvent"],
        start=date(2022, 2, 10),
        end=date(2022, 3, 5),
        to=dest,
    )
    names = sorted(p.relative_to(dest).as_posix() for p in got)
    assert names == [
        "events/event_type=WatchEvent/year=2022/month=02/bq-202202.parquet",
        "events/event_type=WatchEvent/year=2022/month=03/bq-202203.parquet",
    ]
    assert sorted(d for d in api.downloads if d != hf.CATALOG_PATH) == names
    api.downloads.clear()
    sync.pull(
        api, cfg, types=["WatchEvent"], start=date(2022, 2, 10), end=date(2022, 3, 5), to=dest
    )
    assert [d for d in api.downloads if d != hf.CATALOG_PATH] == []  # second pull is a no-op


def test_compact_month_merges_sorts_and_removes_days(cfg, api, lake):
    _june_days(lake)
    n_day = sum(
        pq.ParquetFile(f).metadata.num_rows
        for f in layout.month_dir("WatchEvent", 2023, 6, cfg).glob("day-*.parquet")
    )
    res = compact.compact_month(cfg, 2023, 6, push=False)
    assert res.status == "compacted"
    month = layout.month_file("WatchEvent", 2023, 6, cfg)
    t = pq.read_table(month)
    assert t.num_rows == n_day == 30 * 4
    keys = list(
        zip(
            t["repo_id"].to_pylist(),
            t["created_at"].to_pylist(),
            t["event_id"].to_pylist(),
            strict=True,
        )
    )
    assert keys == sorted(keys)
    assert layout.month_file(layout.PUSH_TYPE, 2023, 6, cfg).exists()
    push = pq.read_table(layout.month_file(layout.PUSH_TYPE, 2023, 6, cfg))
    days = push["day"].to_pylist()
    assert days == sorted(days)
    row = cat.build_catalog(lake.root, files=[month]).to_pylist()[0]
    assert row["kind"] == "month" and row["schema_version"] == 1


def test_compact_push_is_one_atomic_commit_then_deletes_local(cfg, api, lake):
    _june_days(lake)
    day_files = sorted((lake.root).glob("**/day-*.parquet"))
    sync.push_files(api, cfg, lake.root, day_files, "daily")
    api.commits.clear()
    res = compact.compact_month(cfg, 2023, 6, api=api)
    assert res.status == "compacted" and len(res.commits) == 1
    c = api.commits[0]
    assert len(c["adds"]) == 3 + 1  # 2 event types + push_daily + catalog
    assert len(c["deletes"]) == 30 * 3
    remote, _ = sync.fetch_remote_catalog(api, cfg)
    kinds = {r["kind"] for r in remote.to_pylist()}
    assert kinds == {"month"}
    assert not list(lake.root.glob("**/day-*.parquet"))  # local days removed after the commit


def test_compact_is_idempotent(cfg, api, lake):
    _june_days(lake)
    compact.compact_month(cfg, 2023, 6, api=api)
    n = len(api.commits)
    again = compact.compact_month(cfg, 2023, 6, api=api)
    assert again.status == "noop" and len(api.commits) == n


def test_compact_refuses_incomplete_month(cfg, lake):
    lake.day(date(2023, 6, 1))
    # manifest only covers the first day: the rest of the month has no rows
    lake.manifest(date(2023, 6, 1), date(2023, 6, 2), {date(2023, 6, 1)})
    res = compact.compact_month(cfg, 2023, 6, push=False)
    assert res.status == "incomplete" and "not in the manifest" in res.reason
    assert not layout.month_file("WatchEvent", 2023, 6, cfg).exists()


def test_compact_refuses_pending_hours(cfg, lake):
    from breakout.ingest import manifest as mf

    _june_days(lake)
    h = mf.HourlyManifest(layout.hourly_manifest_path(cfg))
    row = list(h.load().values())[10]
    h.upsert([mf.ManifestRow(row.hour_ts, mf.PENDING)])
    res = compact.compact_month(cfg, 2023, 6, push=False)
    assert res.status == "incomplete" and "pending" in res.reason


def test_compact_splits_files_above_the_cap(cfg, lake, monkeypatch):
    monkeypatch.setattr(compact, "ROW_GROUP_SIZE", 2048)  # DuckDB's minimum row group
    for d in range(1, 4):
        lake.day(date(2023, 6, d), n=3000)
    lake.manifest(*JUNE, ok_days={date(2023, 6, d) for d in range(1, 4)})
    res = compact.compact_month(cfg, 2023, 6, push=False, max_file_bytes=1)
    names = sorted(p.name for p in res.written if "WatchEvent" in str(p))
    assert len(names) > 1 and names[0] == "month-202306-part001.parquet"
    rows = [pq.read_table(p)["event_id"].to_pylist() for p in res.written if "WatchEvent" in str(p)]
    assert sum(len(r) for r in rows) == 3 * 3000
    flat = [x for r in rows for x in r]
    assert len(set(flat)) == len(flat)
    # re-running with the default cap replaces the parts by one file, leaving no stale parts
    for d in range(1, 4):
        lake.day(date(2023, 6, d), n=3000)
    compact.compact_month(cfg, 2023, 6, push=False)
    left = sorted(p.name for p in layout.month_dir("WatchEvent", 2023, 6, cfg).glob("month-*"))
    assert left == ["month-202306.parquet"]


def test_compact_not_applicable_before_cutover(cfg, lake):
    lake.day(date(2021, 5, 8))
    assert compact.compact_month(cfg, 2021, 5, push=False).status == "not_applicable"


def test_verify_flags_day_files_overlapping_a_month_file(cfg, lake):
    _june_days(lake, days=range(1, 4))
    compact.compact_month(cfg, 2023, 6, push=False, force=True)
    # day files were not deleted (push=False): both cover June 2023
    msg = "\n".join(verify_lake(cfg).violations)
    assert "overlap a bq/month file" in msg


def test_verify_allows_gap_days_next_to_bq_and_flags_schema_drift(cfg, lake):
    lake.bq("WatchEvent", 2021, 5)
    lake.day(date(2021, 5, 8), types=["WatchEvent"])  # in history.hourly_gap_days
    ok = verify_lake(cfg)
    assert not [v for v in ok.violations if "overlap" in v]
    f = layout.day_file("WatchEvent", date(2021, 5, 8), cfg)
    pq.write_table(pq.read_table(f).drop_columns(["org_id"]), f)
    assert any("differ from schema.py" in v for v in verify_lake(cfg).violations)


def test_verify_remote_detects_mismatch(cfg, api, lake):
    lake.bq("WatchEvent", 2022, 1)
    files = cat.lake_files(lake.root)
    sync.push_files(api, cfg, lake.root, files, "push")
    local = cat.build_catalog(lake.root)
    assert verify_remote(cfg, api, local) == []
    api.repos["u/events"]["events/stray.parquet"] = b"zz"
    problems = verify_remote(cfg, api, local)
    assert any("missing from the remote catalog" in p for p in problems)
    api.repos["u/events"].pop("events/stray.parquet")
    f = files[0].relative_to(lake.root).as_posix()
    api.repos["u/events"][f] = b"tampered"
    assert any("sha/size" in p for p in verify_remote(cfg, api, local))


def test_backfill_month_skips_when_remote_has_month(cfg, api, lake):
    from breakout.lake import backfill_month

    _june_days(lake)
    compact.compact_month(cfg, 2023, 6, api=api)
    calls = []
    run = backfill_month.run_month(cfg, 2023, 6, api=api, ingest=lambda *a, **k: calls.append(a))
    assert run.status == "skipped" and calls == []


def test_backfill_month_ingests_compacts_and_pushes(cfg, api, lake, monkeypatch):
    from datetime import datetime

    from breakout.lake import backfill_month

    def fake_ingest(day, *, cfg, **_):
        lake.day(day, n=2)
        return None

    # manifest rows normally come from ingest_day; pre-seed them for the month
    lake.manifest(*JUNE, ok_days={date(2023, 6, d) for d in range(1, 31)})
    # remove day files so only the fake ingest creates them
    run = backfill_month.run_month(
        cfg, 2023, 6, api=api, ingest=fake_ingest, now=datetime(2023, 8, 1)
    )
    assert run.status == "pushed_month" and run.days == 30
    repo = api.repos["u/events"]
    assert any(p.endswith("month-202306.parquet") for p in repo)
    assert not any("/day-" in p for p in repo)
    assert "manifests/hourly/hourly-202306.parquet" in repo


def test_cards_render_from_schema_and_catalog(cfg, lake):
    from breakout.lake import cards

    lake.bq("WatchEvent", 2022, 1)
    table = cat.build_catalog(lake.root)
    text = cards.render_events(cfg, table)
    assert text.startswith("---\nlicense: mit\n")
    assert "config_name: WatchEvent" in text and "push_daily" in text
    assert "| `repo_id` | int64 | no |" in text
    assert "hf://datasets/u/events/events/event_type=WatchEvent" in text
    assert "no rights in the underlying GitHub events" in text
    for key, body in cards.render_all(cfg, table).items():
        assert body.startswith("---\nlicense: mit"), key


def test_gap_days_are_pushed_as_day_files_next_to_bq(cfg, api, lake):
    from breakout.lake import backfill_month

    cfg.history.hourly_gap_days[:] = [date(2021, 5, 8), date(2021, 5, 10)]

    def fake_ingest(day, *, cfg, **_):
        lake.day(day, n=2)

    lake.manifest(date(2021, 5, 8), date(2021, 5, 9), {date(2021, 5, 8)})
    run = backfill_month.run_gap_days(cfg, api=api, ingest=fake_ingest)
    assert run.status == "pushed_days" and run.days == 2
    repo = api.repos["u/events"]
    assert any(p.endswith("day-2021-05-10.parquet") for p in repo)
    assert "manifests/hourly/hourly-gap-days.parquet" in repo
