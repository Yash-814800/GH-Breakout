"""Typed loader for config/project.yaml — the only module that reads it.

``${VAR}`` placeholders are expanded from the environment. A missing variable yields ``None``;
code that needs the value calls a ``require_*`` accessor, which raises only at that point, so
tests and tooling run without secrets.
"""

from __future__ import annotations

import os
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, model_validator

from breakout.paths import CONFIG_PATH, ROOT

_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class MissingConfigError(RuntimeError):
    """A config value that depends on an unset environment variable was required."""


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCfg(_Section):
    name: str
    package: str
    timezone: str


class HistoryCfg(_Section):
    start_date: date
    cutover_date: date | None = None
    detail_start_date: date | None = None


class EventsCfg(_Section):
    raw_types: list[str]
    aggregated_types: list[str]


class BigQueryCfg(_Section):
    project_id: str | None
    monthly_budget_bytes: int
    per_query_max_bytes_billed: int
    order: str
    manifest_path: str

    def require_project_id(self) -> str:
        if not self.project_id:
            raise MissingConfigError("bigquery.project_id is unset (set GCP_PROJECT_ID)")
        return self.project_id


class HuggingFaceCfg(_Section):
    user: str | None
    events_repo: str | None
    derived_repo: str | None
    snapshots_repo: str | None
    models_repo: str | None
    max_files_per_commit: int

    def _require(self, field: str) -> str:
        value = getattr(self, field)
        if not value:
            raise MissingConfigError(f"huggingface.{field} is unset (set HF_USER)")
        return str(value)

    def require_user(self) -> str:
        return self._require("user")

    def require_events_repo(self) -> str:
        return self._require("events_repo")

    def require_derived_repo(self) -> str:
        return self._require("derived_repo")

    def require_snapshots_repo(self) -> str:
        return self._require("snapshots_repo")

    def require_models_repo(self) -> str:
        return self._require("models_repo")


class LakeCfg(_Section):
    local_root: str
    compression: str
    target_file_mb: int


class CandidatesCfg(_Section):
    max_age_days: int
    max_stars_total: int
    min_stars_14d: int
    exclude_forks: bool
    exclude_bot_owned: bool


class LabelsCfg(_Section):
    horizon_days: int
    primary: str
    relative_quantile: float
    relative_floor_gain: int
    absolute_min_gain: int


class TrainingCfg(_Section):
    snapshot_weekday: int
    first_snapshot: date
    embargo_days: int
    test_window_months: int
    min_train_years: int
    final_train_years: int
    k_values: list[int]


class FeaturesCfg(_Section):
    windows_days: list[int]
    stargazer_activity_lookback_days: int
    session_gap_minutes: int


class DailyCfg(_Section):
    run_hour_utc: int
    min_hour_lag: int
    late_hour_retry_days: int
    recent_window_days: int
    max_runtime_minutes: int


class SiteCfg(_Section):
    deploy_target: str
    leaderboard_size: int
    detail_pages_days: int
    explorer_max_mb: int


class OptionalCfg(_Section):
    hn_enabled: bool
    bluesky_enabled: bool


class Config(_Section):
    project: ProjectCfg
    history: HistoryCfg
    events: EventsCfg
    bigquery: BigQueryCfg
    huggingface: HuggingFaceCfg
    lake: LakeCfg
    candidates: CandidatesCfg
    labels: LabelsCfg
    training: TrainingCfg
    features: FeaturesCfg
    daily: DailyCfg
    site: SiteCfg
    optional: OptionalCfg

    @model_validator(mode="after")
    def _check_embargo(self) -> Config:
        if self.training.embargo_days < self.labels.horizon_days:
            raise ValueError("training.embargo_days must be >= labels.horizon_days")
        return self


def _expand(value: Any) -> Any:
    """Recursively expand ${VAR}; a string referencing any unset/empty variable becomes None."""
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, str) and "${" in value:
        names = _VAR.findall(value)
        if any(not os.environ.get(n) for n in names):
            return None
        return _VAR.sub(lambda m: os.environ[m.group(1)], value)
    return value


def load_config(path: Path | str | None = None) -> Config:
    """Load and validate the config. ``.env`` is loaded only for the default config path."""
    if path is None:
        load_dotenv(ROOT / ".env")
        path = CONFIG_PATH
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return Config.model_validate(_expand(raw))


@lru_cache
def get_config(path: Path | str | None = None) -> Config:
    """Cached :func:`load_config`. Pass a path in tests to use a temporary config."""
    return load_config(path)
