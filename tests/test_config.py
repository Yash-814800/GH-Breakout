from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from breakout.config import MissingConfigError, get_config, load_config


def test_loads_real_config_without_env(temp_config):
    cfg = load_config(temp_config)
    assert cfg.project.name == "gh-breakout"
    assert cfg.history.start_date == date(2015, 1, 1)
    assert cfg.history.cutover_date == date(2023, 6, 1)
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


def test_trusted_era_helpers():
    from datetime import date

    cfg = load_config()
    assert cfg.history.trusted_end == date(2025, 5, 23)
    assert cfg.history.cutover_date == date(2023, 6, 1)
    # 30-day label window [D, D+30) must end on or before 2025-05-23
    assert cfg.latest_trusted_snapshot() == date(2025, 4, 24)
    assert cfg.is_trusted_snapshot(date(2025, 4, 24))
    assert not cfg.is_trusted_snapshot(date(2025, 4, 25))
    assert cfg.era(date(2025, 5, 23)) == "trusted"
    assert cfg.era(date(2025, 5, 24)) == "degraded"
    assert cfg.era(date(2026, 10, 1)) == "degraded"  # no live source approved yet


def test_live_source_defines_live_era(write_config):
    from datetime import date

    def enable(d):
        d["ingest"]["sources"][0]["enabled"] = True
        d["live"] = {"source": "opendigger", "source_start": "2026-09-06"}

    cfg = load_config(write_config(enable))
    assert cfg.era(date(2026, 9, 5)) == "degraded"
    assert cfg.era(date(2026, 9, 6)) == "live"
    assert cfg.is_trusted_day(date(2026, 9, 6)) and not cfg.is_trusted_day(date(2026, 9, 5))


def test_live_config_validation(write_config):
    import pytest

    with pytest.raises(ValueError, match="together"):
        load_config(write_config(lambda d: d["live"].update(source="gharchive")))
    with pytest.raises(ValueError, match="not in ingest.sources"):
        load_config(
            write_config(lambda d: d["live"].update(source="nope", source_start="2026-09-06"))
        )


def test_provisional_windows():
    from datetime import date

    cfg = load_config()  # trusted_end 2025-05-23, no live source
    assert not cfg.window_is_provisional(date(2025, 1, 1), date(2025, 5, 23))
    assert cfg.window_is_provisional(date(2025, 5, 1), date(2025, 5, 24))  # reaches degraded day
    assert cfg.window_is_provisional(date(2026, 10, 1), date(2026, 10, 10))  # all degraded


def test_provisional_windows_with_live_source(write_config):
    from datetime import date

    def enable(d):
        d["ingest"]["sources"][0]["enabled"] = True
        d["live"] = {"source": "opendigger", "source_start": "2026-09-06"}

    cfg = load_config(write_config(enable))
    assert not cfg.window_is_provisional(date(2026, 9, 6), date(2026, 10, 10))
    # a 90-day look-back from 2026-10-10 reaches into the degraded gap
    assert cfg.window_is_provisional(date(2026, 7, 12), date(2026, 10, 9))
    # a window entirely before trusted_end is fine even though it spans nothing degraded
    assert not cfg.window_is_provisional(date(2024, 1, 1), date(2024, 12, 31))


def test_sources_priority_and_availability(write_config):
    from datetime import date

    def enable(d):
        d["ingest"]["sources"][0]["enabled"] = True

    cfg = load_config(write_config(enable))
    before = [s.name for s in cfg.ingest.sources_for(date(2026, 9, 5))]
    after = [s.name for s in cfg.ingest.sources_for(date(2026, 9, 6))]
    assert before == ["gharchive"]
    assert after == ["opendigger", "gharchive"]
    # shipped config keeps OpenDigger disabled until validated
    assert [s.name for s in load_config().ingest.sources_for(date(2026, 9, 6))] == ["gharchive"]


def test_at_least_one_source_enabled(write_config):
    import pytest

    def disable(d):
        for s in d["ingest"]["sources"]:
            s["enabled"] = False

    with pytest.raises(ValueError, match="enabled source"):
        load_config(write_config(disable))
