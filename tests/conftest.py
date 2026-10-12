from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from breakout.paths import CONFIG_PATH

ENV_NAMES = (
    "HF_TOKEN",
    "HF_USER",
    "GH_ENRICH_TOKEN",
    "GCP_PROJECT_ID",
    "BLUESKY_HANDLE",
    "BLUESKY_APP_PASSWORD",
    "LOG_LEVEL",
    "BREAKOUT_CONFIG",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def temp_config(tmp_path: Path) -> Path:
    """A copy of the real project.yaml in a temp dir."""
    dest = tmp_path / "project.yaml"
    dest.write_text(CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


@pytest.fixture
def write_config(tmp_path: Path):
    def _write(mutate) -> Path:
        data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        mutate(data)
        dest = tmp_path / "custom.yaml"
        dest.write_text(yaml.safe_dump(data), encoding="utf-8")
        return dest

    return _write
