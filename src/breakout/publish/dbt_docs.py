"""dbt docs for the website and the generated data dictionary (Phase 13.2).

``breakout publish dbt-docs`` runs ``dbt docs generate`` and copies ``index.html``,
``manifest.json`` and ``catalog.json`` to ``site/public/dbt-docs/``.

A clean CI runner has no warehouse, so the docs are generated with ``--empty-catalog`` (lineage and
descriptions come from the project files) and the column types come from a catalog that was
generated once against the real warehouse and is committed as ``reports/dbt/catalog.json``
(``--refresh-catalog`` rewrites it, local machine only).

``breakout publish data-dictionary`` renders ``docs/data_dictionary.md`` from ``manifest.json``.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from breakout import paths as P
from breakout.config import Config
from breakout.dbt_runner import DBT_DIR, run_dbt
from breakout.logging import get_logger

log = get_logger(__name__)

SITE_DOCS_DIR = P.ROOT / "site" / "public" / "dbt-docs"
COMMITTED_CATALOG = P.ROOT / "reports" / "dbt" / "catalog.json"
SUMMARY_JSON = P.ROOT / "reports" / "dbt" / "summary.json"
DATA_DICTIONARY_MD = P.ROOT / "docs" / "data_dictionary.md"
LAYERS = ("staging", "intermediate", "features", "marts")
DOC_FILES = ("index.html", "manifest.json", "catalog.json")


def _target() -> Path:
    return DBT_DIR / "target"


def generate(cfg: Config) -> None:
    """``dbt docs generate --empty-catalog`` against an empty scratch lake and warehouse.

    The empty catalog needs no data, and compiling the staging models lists the lake files
    (thousands of files on the external disk) and would open the 33 GB warehouse; neither is
    needed for lineage and descriptions.
    """
    scratch = P.TMP_DIR / "dbt_docs"
    shutil.rmtree(scratch, ignore_errors=True)
    (scratch / "lake").mkdir(parents=True)
    try:
        rc = run_dbt(
            cfg,
            ["docs", "generate", "--empty-catalog"],
            lake=scratch / "lake",
            warehouse=scratch / "docs.duckdb",
        )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if rc != 0:
        raise RuntimeError(f"dbt docs generate failed with exit code {rc}")


def fill_catalog(manifest: dict[str, Any], committed: dict[str, Any]) -> dict[str, Any]:
    """A catalog with the committed column types for every model that is still in the manifest.

    ``committed`` is a dbt catalog; nodes that no longer exist are dropped, new nodes keep the
    empty entry dbt wrote.
    """
    nodes = {
        uid: n for uid, n in committed.get("nodes", {}).items() if uid in manifest.get("nodes", {})
    }
    return {**committed, "nodes": nodes, "sources": committed.get("sources", {})}


def catalog_from_warehouse(manifest: dict[str, Any], warehouse: Path) -> dict[str, Any]:
    """A dbt-format catalog read from the information schema of the local warehouse.

    Metadata queries only (``dbt docs generate`` without ``--empty-catalog`` also binds every view
    over the lake, which takes much longer than the information schema on the 33 GB file).
    """
    from breakout.duck import connect

    con = connect(warehouse, read_only=True)
    try:
        kinds = dict(
            con.execute(
                "select table_name, table_type from information_schema.tables "
                "where table_schema = 'main'"
            ).fetchall()
        )
        cols: dict[str, list[tuple[str, str]]] = {}
        for t, c, d in con.execute(
            "select table_name, column_name, data_type from information_schema.columns "
            "where table_schema = 'main' order by table_name, ordinal_position"
        ).fetchall():
            cols.setdefault(t, []).append((c, d))
    finally:
        con.close()
    nodes: dict[str, Any] = {}
    for uid, n in manifest["nodes"].items():
        if n["resource_type"] not in ("model", "seed"):
            continue
        rel = n.get("alias") or n["name"]
        if rel not in cols:
            continue
        nodes[uid] = {
            "metadata": {
                "type": kinds.get(rel, "BASE TABLE"),
                "schema": "main",
                "name": rel,
                "database": "warehouse",
                "comment": None,
                "owner": None,
            },
            "columns": {
                c: {"type": d, "index": i, "name": c, "comment": None}
                for i, (c, d) in enumerate(cols[rel], 1)
            },
            "stats": {},
            "unique_id": uid,
        }
    return {
        "metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/catalog/v1.json",
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "env": {},
        },
        "nodes": nodes,
        "sources": {},
        "errors": None,
    }


def manifest_summary(manifest: dict[str, Any]) -> dict[str, int]:
    """Counts shown on the status page and in the README."""
    nodes = manifest["nodes"].values()
    models = [n for n in nodes if n["resource_type"] == "model"]
    return {
        "models": len(models),
        "tests": sum(1 for n in nodes if n["resource_type"] == "test"),
        "columns": sum(len(n.get("columns", {})) for n in models),
    }


def publish_docs(
    cfg: Config, *, refresh_catalog: bool = False, out_dir: Path | None = None
) -> Path:
    out = out_dir or SITE_DOCS_DIR
    generate(cfg)
    t = _target()
    manifest = json.loads((t / "manifest.json").read_text())
    if refresh_catalog:
        cat = catalog_from_warehouse(manifest, P.WAREHOUSE)
        COMMITTED_CATALOG.parent.mkdir(parents=True, exist_ok=True)
        COMMITTED_CATALOG.write_text(json.dumps(cat, indent=1, sort_keys=True) + "\n")
        log.info("Refreshed %s (%d models)", COMMITTED_CATALOG, len(cat["nodes"]))
    if COMMITTED_CATALOG.exists():
        cat = fill_catalog(manifest, json.loads(COMMITTED_CATALOG.read_text()))
        (t / "catalog.json").write_text(json.dumps(cat))
    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(json.dumps(manifest_summary(manifest)) + "\n")
    out.mkdir(parents=True, exist_ok=True)
    for name in DOC_FILES:
        shutil.copy2(t / name, out / name)
    log.info("dbt docs copied to %s", out)
    return out


# -----------------------------------------------------------------------------
# data dictionary
# -----------------------------------------------------------------------------


def _layer(node: dict[str, Any]) -> str:
    parts = node.get("path", "").split("/")
    return parts[0] if parts and parts[0] in LAYERS else "other"


def _cell(text: str | None) -> str:
    return " ".join((text or "").split()).replace("|", "\\|") or "-"


def data_dictionary_md(manifest: dict[str, Any], catalog: dict[str, Any] | None = None) -> str:
    """Markdown with one section per model (grouped by layer) and a table of its columns."""
    cat_nodes = (catalog or {}).get("nodes", {})
    models = [n for n in manifest["nodes"].values() if n["resource_type"] == "model"]
    tests_on: dict[str, int] = {}
    for n in manifest["nodes"].values():
        if n["resource_type"] == "test":
            for dep in n.get("depends_on", {}).get("nodes", []):
                tests_on[dep] = tests_on.get(dep, 0) + 1
    out = [
        "# Data dictionary",
        "",
        "Generated by `uv run breakout publish data-dictionary` from the dbt `manifest.json`; "
        "do not edit by hand. Descriptions live in `dbt/models/**/_*.yml`. The model input columns "
        "(features) are described in more detail, with leakage notes and SHAP sentences, in "
        "`config/feature_dictionary.yaml`.",
        "",
        f"{len(models)} models, "
        f"{sum(len(n.get('columns', {})) for n in models)} documented columns, "
        f"{sum(tests_on.get(n['unique_id'], 0) for n in models)} tests.",
        "",
    ]
    for layer in LAYERS:
        group = sorted((n for n in models if _layer(n) == layer), key=lambda n: n["name"])
        if not group:
            continue
        out += [f"## {layer.capitalize()} models", ""]
        for n in group:
            mat = n.get("config", {}).get("materialized", "?")
            deps = sorted(
                d.split(".")[-1]
                for d in n.get("depends_on", {}).get("nodes", [])
                if d.split(".")[0] in ("model", "seed", "source")
            )
            out += [
                f"### `{n['name']}`",
                "",
                _cell(n.get("description")),
                "",
                f"Materialized as **{mat}**. Tests: {tests_on.get(n['unique_id'], 0)}. "
                + (f"Built from: {', '.join(f'`{d}`' for d in deps)}." if deps else ""),
                "",
                "| Column | Type | Description |",
                "|---|---|---|",
            ]
            types = {
                c.lower(): v.get("type", "")
                for c, v in cat_nodes.get(n["unique_id"], {}).get("columns", {}).items()
            }
            for cname, c in n.get("columns", {}).items():
                ctype = types.get(cname.lower(), "") or "-"
                out.append(f"| `{cname}` | {ctype} | {_cell(c.get('description'))} |")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def write_data_dictionary(
    cfg: Config | None = None, manifest_path: Path | None = None, out: Path | None = None
) -> Path:
    """Render the dictionary; with ``cfg`` the manifest is refreshed first (``dbt parse``)."""
    if cfg is not None:
        rc = run_dbt(cfg, ["parse"])
        if rc != 0:
            raise RuntimeError(f"dbt parse failed with exit code {rc}")
    manifest = json.loads((manifest_path or _target() / "manifest.json").read_text())
    catalog = json.loads(COMMITTED_CATALOG.read_text()) if COMMITTED_CATALOG.exists() else None
    path = out or DATA_DICTIONARY_MD
    path.write_text(data_dictionary_md(manifest, catalog))
    return path
