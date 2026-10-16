from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from breakout.config import load_config
from breakout.enrich import github_meta as gm
from breakout.enrich import http as H

FIX = Path(__file__).parent.parent / "fixtures"
NOW = datetime(2026, 10, 16, 12, 0)


def _api(handler) -> H.GitHubApi:
    return H.GitHubApi(
        "t",
        client=H.make_client("u", transport=httpx.MockTransport(handler)),
        clock=H.FakeClock(),
    )


def test_parse_graphql_nodes() -> None:
    body = json.loads((FIX / "github_graphql_batch.json").read_text())
    nodes = body["data"]["nodes"]
    user = gm.parse_graphql_repo(101, nodes[0], NOW)
    assert user["status"] == "ok" and user["source"] == "graphql"
    assert user["created_at"] == datetime(2024, 3, 1, 12, 30)
    assert user["owner_type"] == "User" and user["primary_language"] == "Python"
    assert user["topics"] == ["ml", "cli"] and user["is_fork"] is False
    org = gm.parse_graphql_repo(102, nodes[1], NOW)
    assert org["owner_type"] == "Organization" and org["primary_language"] is None
    assert set(user) == set(gm.SCHEMA.names)


def test_parse_rest_repo() -> None:
    row = gm.parse_rest_repo(103, json.loads((FIX / "github_rest_repo.json").read_text()), NOW)
    assert row["is_fork"] is True and row["parent_repo_id"] == 42
    assert row["license_spdx"] == "Apache-2.0" and row["owner_created_at"] is None
    assert row["is_mirror"] is False and row["is_archived"] is True


def test_node_id_is_legacy_global_id() -> None:
    assert gm.node_id(1) == "MDEwOlJlcG9zaXRvcnkx"  # base64("010:Repository1")


def test_fetch_batch_by_node_id_null_and_mismatch() -> None:
    gql = (FIX / "github_graphql_batch.json").read_text()
    rest = json.loads((FIX / "github_rest_repo.json").read_text())
    seen: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/graphql":
            seen.append(json.loads(req.content))
            return httpx.Response(200, text=gql, headers={"content-type": "application/json"})
        if req.url.path == "/repositories/104":  # fixture node 3 has databaseId 555: re-check
            return httpx.Response(404, json={"message": "Not Found"})
        if req.url.path == "/repositories/103":
            return httpx.Response(200, json=rest)
        return httpx.Response(500)

    stats = gm.FetchStats()
    rows = gm.fetch_batch(_api(handler), [101, 102, 103, 104], stats, now=lambda: NOW)
    assert seen[0]["variables"]["ids"] == [gm.node_id(i) for i in (101, 102, 103, 104)]
    by = {r["repo_id"]: r for r in rows}
    assert by[101]["status"] == "ok" and by[102]["owner_type"] == "Organization"
    assert by[103]["status"] == "not_found" and by[103]["source"] == "graphql"  # null node: kept
    assert by[104]["status"] == "not_found" and by[104]["source"] == "rest"  # id mismatch -> REST
    assert (stats.ok, stats.not_found, stats.id_mismatch, stats.rest_fallbacks) == (2, 2, 1, 1)
    assert [r["repo_id"] for r in rows] == [101, 102, 103, 104]  # order preserved


def test_shard_consolidate_keeps_newest_and_fresh_skips(tmp_path: Path, write_config) -> None:
    def mutate(d: dict) -> None:
        d["enrich"]["output_dir"] = str(tmp_path / "enrich")
        d["lake"]["local_root"] = str(tmp_path / "lake")

    cfg = load_config(write_config(mutate))
    old = gm._row(1, "ok", "graphql", datetime(2020, 1, 1))
    new = gm._row(1, "not_found", "rest", datetime(2026, 10, 1))
    other = gm._row(2, "ok", "graphql", datetime(2026, 10, 15))
    gm.write_shard(cfg, [old, other], 1)
    assert gm.consolidate(cfg) == 2
    gm.write_shard(cfg, [new], 2)
    assert gm.consolidate(cfg) == 2
    t = pq.read_table(tmp_path / "enrich" / gm.METADATA)
    assert t.schema.equals(gm.SCHEMA)
    assert {r["repo_id"]: r["status"] for r in t.to_pylist()} == {1: "not_found", 2: "ok"}
    assert gm.fresh_ids(cfg, 100000) == {1, 2}


def test_build_targets_window_logic(tmp_path: Path, write_config) -> None:
    lake = tmp_path / "lake"

    def mutate(d: dict) -> None:
        d["enrich"]["output_dir"] = str(tmp_path / "enrich")
        d["lake"]["local_root"] = str(lake)

    cfg = load_config(write_config(mutate))
    rows = []
    # repo 1: 5 stars within 3 days right at birth -> target
    rows += [(1, datetime(2024, 1, 1 + i // 2, 3)) for i in range(5)]
    # repo 2: 5 stars spread 20 days apart -> never 5 in 14 days
    rows += [(2, datetime(2024, 1, 1 + 20 * i // 4 * 1, 3)) for i in range(5)]
    # repo 3: 1 star then, 200 days later, 5 stars in a burst (window start > 120 days) -> not
    rows += [(3, datetime(2023, 6, 1, 3))]
    rows += [(3, datetime(2023, 12, 20, 3))] * 5
    d = lake / "events" / "event_type=WatchEvent" / "year=2024" / "month=01"
    d.mkdir(parents=True)
    pq.write_table(
        pa.table(
            {
                "repo_id": [r[0] for r in rows if r[1].year == 2024],
                "created_at": pa.array(
                    [r[1] for r in rows if r[1].year == 2024], pa.timestamp("us")
                ),
            }
        ),
        d / "month-202401.parquet",
    )
    d2 = lake / "events" / "event_type=WatchEvent" / "year=2023" / "month=06"
    d2.mkdir(parents=True)
    pq.write_table(
        pa.table(
            {"repo_id": [3], "created_at": pa.array([datetime(2023, 6, 1, 3)], pa.timestamp("us"))}
        ),
        d2 / "month-202306.parquet",
    )
    d3 = lake / "events" / "event_type=WatchEvent" / "year=2023" / "month=12"
    d3.mkdir(parents=True)
    pq.write_table(
        pa.table(
            {
                "repo_id": [3] * 5,
                "created_at": pa.array([datetime(2023, 12, 20, 3)] * 5, pa.timestamp("us")),
            }
        ),
        d3 / "month-202312.parquet",
    )
    out = gm.build_targets(cfg)
    got = pq.read_table(tmp_path / "enrich" / gm.TARGETS).to_pylist()
    assert [r["repo_id"] for r in got] == [1]
    assert got[0]["max_stars_window"] == 5
    assert out["targets"] == 1
    assert pytest is not None
