"""Typed loader for config/project.yaml — the only module that reads it.

``${VAR}`` placeholders are expanded from the environment. A missing variable yields ``None``;
code that needs the value calls a ``require_*`` accessor, which raises only at that point, so
tests and tooling run without secrets.
"""

from __future__ import annotations

import os
import re
from datetime import date, timedelta
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
    trusted_end: date
    hourly_gap_days: list[date] = []

    @model_validator(mode="after")
    def _check_eras(self) -> HistoryCfg:
        if self.trusted_end < self.start_date:
            raise ValueError("history.trusted_end must be >= history.start_date")
        if self.cutover_date is not None and self.cutover_date <= self.start_date:
            raise ValueError("history.cutover_date must be > history.start_date")
        for d in self.hourly_gap_days:
            if self.cutover_date is not None and d >= self.cutover_date:
                raise ValueError("history.hourly_gap_days must be before cutover_date")
        return self


class LiveCfg(_Section):
    """Which source feeds live scoring. Null until a source is validated and approved."""

    source: str | None = None
    source_start: date | None = None

    @model_validator(mode="after")
    def _both_or_neither(self) -> LiveCfg:
        if (self.source is None) != (self.source_start is None):
            raise ValueError("live.source and live.source_start must be set together")
        return self


class SourceCfg(_Section):
    name: str
    base_url: str
    available_from: date | None = None
    has_manifest: bool = False
    # dotted JSON paths inside the manifest: {"sha256": ..., "events": ...}. Left null until a real
    # manifest has been observed (OpenDigger manifests returned 404 on 2026-10-12, ADR-009).
    manifest_keys: dict[str, str] | None = None
    enabled: bool = True


class IngestCfg(_Section):
    sources: list[SourceCfg]

    @model_validator(mode="after")
    def _check_sources(self) -> IngestCfg:
        names = [s.name for s in self.sources]
        if len(set(names)) != len(names):
            raise ValueError("ingest.sources names must be unique")
        if not any(s.enabled for s in self.sources):
            raise ValueError("ingest.sources needs at least one enabled source")
        return self

    def sources_for(self, day: date) -> list[SourceCfg]:
        """Enabled sources that exist for ``day``, in priority order."""
        return [
            s
            for s in self.sources
            if s.enabled and (s.available_from is None or day >= s.available_from)
        ]


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
    max_bytes_per_commit: int

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
    max_file_mb: int


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


class TastemakerCfg(_Section):
    """Co-star ('tastemaker') score parameters (Phase 7, ADR-022)."""

    lookahead_days: int  # an early star is a hit if the repo gains >= absolute_min_gain within this
    alpha: float  # smoothing: score = (hits + alpha) / (early_stars + alpha + beta)
    beta: float
    min_known: int  # early stars needed before an actor can be in the top-quantile group
    top_quantile: float  # share of such actors that counts as 'top' (0.01 = top 1%)


class FeaturesCfg(_Section):
    windows_days: list[int]
    stargazer_activity_lookback_days: int
    session_gap_minutes: int
    tastemaker: TastemakerCfg
    payload_trim_date: date  # PR merged flag / author vanish from this day on (ADR-003/007)


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


class EnrichCfg(_Section):
    """Phase 4 enrichment parameters (ADR-016)."""

    output_dir: str  # local output root; mirrored under `hf_prefix` in the derived repo
    hf_prefix: str
    repo_url: str  # shown in the User-Agent
    max_rps: float  # hard ceiling on outbound requests per second per host
    graphql_batch_size: int
    workers: int  # concurrent GraphQL batches; the shared throttle still caps requests at max_rps
    meta_max_age_days: int
    target_window_days: (
        int  # a repo is a target when it got >= candidates.min_stars_14d in a window
    )
    target_first_seen_days: int  # ...starting within this many days of its first observed event
    actor_samples: int
    actor_holdout_frac: float
    hn_start: date
    hn_initial_window_days: int


class OptionalCfg(_Section):
    hn_enabled: bool
    bluesky_enabled: bool


class Config(_Section):
    project: ProjectCfg
    history: HistoryCfg
    events: EventsCfg
    ingest: IngestCfg
    live: LiveCfg
    bigquery: BigQueryCfg
    huggingface: HuggingFaceCfg
    lake: LakeCfg
    candidates: CandidatesCfg
    labels: LabelsCfg
    training: TrainingCfg
    features: FeaturesCfg
    daily: DailyCfg
    enrich: EnrichCfg
    site: SiteCfg
    optional: OptionalCfg

    @model_validator(mode="after")
    def _check_embargo(self) -> Config:
        if self.training.embargo_days < self.labels.horizon_days:
            raise ValueError("training.embargo_days must be >= labels.horizon_days")
        if self.live.source is not None and self.live.source not in {
            s.name for s in self.ingest.sources
        }:
            raise ValueError(f"live.source {self.live.source!r} is not in ingest.sources")
        return self

    def latest_trusted_snapshot(self) -> date:
        """Last snapshot date D whose label window [D, D+h) ends on or before ``trusted_end``.

        Features for D use events < D, so the feature window ends earlier than the label window.
        """
        return self.history.trusted_end - timedelta(days=self.labels.horizon_days - 1)

    def is_trusted_snapshot(self, snapshot: date) -> bool:
        return snapshot <= self.latest_trusted_snapshot()

    def era(self, day: date) -> str:
        """``trusted`` (<= trusted_end), ``live`` (>= live.source_start, once a live source is
        approved) or ``degraded`` (everything in between: kept and flagged, never trained on)."""
        if day <= self.history.trusted_end:
            return "trusted"
        if self.live.source_start is not None and day >= self.live.source_start:
            return "live"
        return "degraded"

    def is_trusted_day(self, day: date) -> bool:
        """Star data for ``day`` comes from a trusted source (trusted GH Archive era or the
        approved live source)."""
        return self.era(day) != "degraded"

    def window_is_provisional(self, start: date, end: date) -> bool:
        """True when any day in ``[start, end]`` is not from a trusted source.

        A live feature (or label window) whose look-back overlaps such days is flagged
        ``provisional``: shown as such on the leaderboard and excluded from headline track-record
        metrics (ADR-010).
        """
        if end < start:
            raise ValueError("end must be >= start")
        if start > self.history.trusted_end:
            return self.live.source_start is None or start < self.live.source_start
        # window starts in the trusted era: provisional iff it reaches into the degraded gap
        gap_start = self.history.trusted_end + timedelta(days=1)
        gap_end = (
            self.live.source_start - timedelta(days=1)
            if self.live.source_start is not None
            else date.max
        )
        return end >= gap_start and start <= gap_end


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
