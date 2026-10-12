from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from breakout.config import MissingConfigError, get_config, load_config


def test_loads_real_config_without_env(temp_config):
    cfg = load_config(temp_config)
    assert cfg.project.name == "gh-breakout"
    assert cfg.history.start_date == date(2015, 1, 1)
    assert cfg.history.cutover_date is None
    assert cfg.training.first_snapshot == date(2016, 1, 4)
    assert cfg.labels.horizon_days == 30


def test_missing_env_is_none_and_require_raises(temp_config):
    cfg = load_config(temp_config)
    assert cfg.huggingface.events_repo is None
    assert cfg.bigquery.project_id is None
    with pytest.raises(MissingConfigError):
        cfg.huggingface.require_events_repo()
    with pytest.raises(MissingConfigError):
        cfg.bigquery.require_project_id()


def test_env_expansion(temp_config, monkeypatch):
    monkeypatch.setenv("HF_USER", "alice")
    monkeypatch.setenv("GCP_PROJECT_ID", "proj-1")
    cfg = load_config(temp_config)
    assert cfg.huggingface.user == "alice"
    assert cfg.huggingface.require_events_repo() == "alice/gh-breakout-events"
    assert cfg.bigquery.require_project_id() == "proj-1"


def test_embargo_must_cover_horizon(write_config):
    path = write_config(lambda d: d["training"].update(embargo_days=7))
    with pytest.raises(ValidationError):
        load_config(path)


def test_unknown_key_rejected(write_config):
    path = write_config(lambda d: d["labels"].update(typo=1))
    with pytest.raises(ValidationError):
        load_config(path)


def test_get_config_is_cached(temp_config):
    assert get_config(temp_config) is get_config(temp_config)
