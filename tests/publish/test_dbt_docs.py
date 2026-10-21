"""Unit tests for the dbt docs helpers and the data dictionary (Phase 13.2)."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from breakout.publish import dbt_docs

MANIFEST = {
    "nodes": {
        "model.breakout.stg_a": {
            "unique_id": "model.breakout.stg_a",
            "resource_type": "model",
            "name": "stg_a",
            "path": "staging/stg_a.sql",
            "description": "Stars | per day.",
            "config": {"materialized": "view"},
            "depends_on": {"nodes": ["source.breakout.lake.a"]},
            "columns": {
                "repo_id": {"description": "Repo id."},
                "n": {"description": "Count\nof stars."},
            },
        },
        "model.breakout.mart_b": {
            "unique_id": "model.breakout.mart_b",
            "resource_type": "model",
            "name": "mart_b",
            "path": "marts/mart_b.sql",
            "description": "Mart.",
            "config": {"materialized": "table"},
            "depends_on": {"nodes": ["model.breakout.stg_a"]},
            "columns": {"repo_id": {"description": "Repo id."}},
        },
        "test.breakout.t1": {
            "unique_id": "test.breakout.t1",
            "resource_type": "test",
            "depends_on": {"nodes": ["model.breakout.mart_b"]},
        },
        "seed.breakout.known": {
            "unique_id": "seed.breakout.known",
            "resource_type": "seed",
            "name": "known",
        },
    }
}
CATALOG = {
    "nodes": {
        "model.breakout.stg_a": {
            "columns": {"REPO_ID": {"type": "BIGINT"}, "n": {"type": "INTEGER"}}
        },
        "model.breakout.gone": {"columns": {"x": {"type": "INTEGER"}}},
    },
    "sources": {},
}


def test_data_dictionary_lists_layers_columns_types_and_tests():
    md = dbt_docs.data_dictionary_md(MANIFEST, CATALOG)
    assert md.index("## Staging models") < md.index("## Marts models")
    assert "2 models, 3 documented columns, 1 tests." in md
    assert "Stars \\| per day." in md  # pipes are escaped for the table
    assert "| `repo_id` | BIGINT | Repo id. |" in md  # type lookup ignores case
    assert "| `n` | INTEGER | Count of stars. |" in md  # newlines collapse
    assert "Built from: `a`." in md and "Built from: `stg_a`." in md
    assert "Tests: 1." in md


def test_data_dictionary_is_deterministic():
    assert dbt_docs.data_dictionary_md(MANIFEST, CATALOG) == dbt_docs.data_dictionary_md(
        MANIFEST, CATALOG
    )


def test_fill_catalog_drops_models_that_no_longer_exist():
    out = dbt_docs.fill_catalog(MANIFEST, CATALOG)
    assert set(out["nodes"]) == {"model.breakout.stg_a"}


def test_catalog_from_warehouse_reads_types_and_kinds(tmp_path: Path):
    wh = tmp_path / "w.duckdb"
    con = duckdb.connect(str(wh))
    con.execute("create table stg_a (repo_id bigint, n integer)")
    con.execute("create view mart_b as select 1::bigint as repo_id")
    con.close()
    cat = dbt_docs.catalog_from_warehouse(MANIFEST, wh)
    a = cat["nodes"]["model.breakout.stg_a"]
    assert a["metadata"]["type"] == "BASE TABLE"
    assert {c: v["type"] for c, v in a["columns"].items()} == {"repo_id": "BIGINT", "n": "INTEGER"}
    assert cat["nodes"]["model.breakout.mart_b"]["metadata"]["type"] == "VIEW"
    json.dumps(cat)  # serialisable
