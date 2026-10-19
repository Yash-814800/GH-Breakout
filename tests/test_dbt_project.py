"""Static checks on the dbt project and the CLI wrapper (no data needed)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from breakout import paths as P
from breakout.config import get_config
from breakout.dbt_runner import config_vars, dbt_env, history_vars, merge_vars

DBT = P.ROOT / "dbt"
MODELS = sorted((DBT / "models").rglob("*.sql"))
JOIN_RE = re.compile(r"\b(join|using|on)\b", re.I)


def _code_lines(path: Path):
    """SQL lines without ``--`` comments and without Jinja comment blocks."""
    text = re.sub(r"\{#.*?#\}", "", path.read_text(), flags=re.S)
    for no, line in enumerate(text.splitlines(), 1):
        line = line.split("--", 1)[0]
        if line.strip():
            yield no, line


def test_no_model_joins_on_repo_name():
    offenders = []
    for path in MODELS:
        for no, line in _code_lines(path):
            if "repo_name" in line and JOIN_RE.search(line):
                offenders.append(f"{path.relative_to(P.ROOT)}:{no}: {line.strip()}")
    assert not offenders, "models must join on repo_id, never repo_name:\n" + "\n".join(offenders)


def test_repo_name_join_check_detects_a_violation(tmp_path):
    bad = tmp_path / "m.sql"
    bad.write_text("select 1 from a join b on a.repo_name = b.repo_name\n")
    assert any("repo_name" in line and JOIN_RE.search(line) for _, line in _code_lines(bad))


def test_every_model_has_a_yaml_entry():
    declared: set[str] = set()
    for yml in (DBT / "models").rglob("*.yml"):
        doc = yaml.safe_load(yml.read_text()) or {}
        declared |= {m["name"] for m in doc.get("models", [])}
    missing = {p.stem for p in MODELS} - declared
    assert not missing, f"models without a YAML entry (description + tests): {sorted(missing)}"


def test_every_model_yaml_entry_has_description_and_a_grain_test():
    for yml in (DBT / "models").rglob("*.yml"):
        for m in (yaml.safe_load(yml.read_text()) or {}).get("models", []):
            assert m.get("description"), f"{m['name']} lacks a description"
            col_tests = [t for c in m.get("columns", []) for t in c.get("tests", [])]
            assert m.get("tests") or col_tests, f"{m['name']} has no tests"


def test_no_select_star_from_sources():
    for path in MODELS:
        for no, line in _code_lines(path):
            assert not re.search(r"select\s+\*\s+from\s+\{\{\s*source", line, re.I), (path, no)


def test_dbt_env_uses_absolute_paths_and_caps(tmp_path):
    env = dbt_env(
        {}, lake=tmp_path / "lake", derived=tmp_path / "d", warehouse=tmp_path / "w.duckdb"
    )
    for k in ("GHB_LAKE", "GHB_DERIVED", "GHB_WAREHOUSE", "DBT_PROFILES_DIR", "GHB_DUCKDB_TMP"):
        assert Path(env[k]).is_absolute()
    assert env["GHB_DUCKDB_THREADS"] == "1"
    assert env["GHB_DUCKDB_MEMORY"].endswith("MB")


def test_dbt_env_keeps_user_overrides():
    env = dbt_env({"GHB_DUCKDB_MEMORY": "3GB", "GHB_WAREHOUSE": "/x/y.duckdb"})
    assert env["GHB_DUCKDB_MEMORY"] == "3GB"
    assert env["GHB_WAREHOUSE"] == "/x/y.duckdb"


def test_config_vars_come_from_config():
    cfg = get_config(None)
    v = config_vars(cfg)
    assert v["min_stars_14d"] == cfg.candidates.min_stars_14d
    assert v["max_age_days"] == cfg.candidates.max_age_days
    assert v["session_gap_minutes"] == cfg.features.session_gap_minutes
    assert v["max_stars_total"] == cfg.candidates.max_stars_total
    assert v["horizon_days"] == cfg.labels.horizon_days
    assert v["relative_quantile"] == cfg.labels.relative_quantile
    assert v["first_snapshot"] == cfg.training.first_snapshot.isoformat()
    assert v["snapshot_weekday"] == cfg.training.snapshot_weekday
    h = history_vars(cfg)
    assert h["events_start"] == cfg.history.start_date.isoformat()
    assert h["events_end"] > cfg.history.trusted_end.isoformat()  # exclusive end


def test_merge_vars_user_values_win():
    out = merge_vars(
        ["run", "--vars", "{events_start: 2025-04-01, max_age_days: 30}"],
        {"max_age_days": 90, "a": 1},
    )
    assert out[:1] == ["run"] and "--vars" in out
    merged = json.loads(out[out.index("--vars") + 1])
    assert (
        merged["max_age_days"] == 30 and merged["a"] == 1 and merged["events_start"] == "2025-04-01"
    )


def test_merge_vars_without_user_vars_appends():
    out = merge_vars(["build", "--select", "staging"], {"a": 1})
    assert json.loads(out[-1]) == {"a": 1}
