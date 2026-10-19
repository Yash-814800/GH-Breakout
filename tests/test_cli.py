from __future__ import annotations

import pytest
from typer.testing import CliRunner

from breakout.cli import app

runner = CliRunner()
GROUPS = ["ingest", "backfill", "lake", "enrich", "build", "ml", "daily", "publish", "ops"]
STUB_GROUPS = [
    g for g in GROUPS if g not in ("ingest", "backfill", "lake", "enrich", "build", "ml")
]  # real groups


def test_help_lists_groups():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for group in GROUPS:
        assert group in result.output


@pytest.mark.parametrize("group", STUB_GROUPS)
def test_stub_groups(group):
    result = runner.invoke(app, [group])
    assert result.exit_code == 0
    assert "not implemented yet (Phase" in result.output


def test_ml_group_lists_baseline():
    result = runner.invoke(app, ["ml", "--help"])
    assert result.exit_code == 0
    assert "baseline" in result.output


def test_build_group_lists_labels():
    result = runner.invoke(app, ["build", "--help"])
    assert "labels" in result.output


def test_ingest_group_lists_commands():
    result = runner.invoke(app, ["ingest", "--help"])
    assert result.exit_code == 0
    for command in ("hour", "day", "range", "audit"):
        assert command in result.output


def test_backfill_group_lists_commands():
    result = runner.invoke(app, ["backfill", "--help"])
    assert result.exit_code == 0
    for command in ("survey", "plan"):
        assert command in result.output


def test_info_empty_env(temp_config):
    result = runner.invoke(app, ["--config", str(temp_config), "info"])
    assert result.exit_code == 0, result.output
    assert "HF_TOKEN: not set" in result.output
    assert "gh-breakout" in result.output


def test_info_masks_secrets(temp_config, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_supersecretvalue")
    monkeypatch.setenv("GH_ENRICH_TOKEN", "ghp_anothersecret")
    result = runner.invoke(app, ["--config", str(temp_config), "info"])
    assert result.exit_code == 0
    assert "HF_TOKEN: set" in result.output
    assert "supersecret" not in result.output
    assert "anothersecret" not in result.output


def test_enrich_group_lists_commands():
    result = runner.invoke(app, ["enrich", "--help"])
    assert result.exit_code == 0
    for command in (
        "names",
        "targets",
        "repos",
        "actor-age",
        "trending-history",
        "trending-today",
        "hn-history",
        "hn-recent",
        "upload",
    ):
        assert command in result.output


def test_build_group_lists_commands():
    result = runner.invoke(app, ["build", "--help"])
    assert result.exit_code == 0
    for command in ("dbt", "history"):
        assert command in result.output
