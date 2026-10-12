from __future__ import annotations

from pathlib import Path

import pytest

from breakout.config import Config, load_config


@pytest.fixture
def cfg(write_config, tmp_path: Path) -> Config:
    def mutate(d: dict) -> None:
        d["lake"]["local_root"] = str(tmp_path / "data" / "lake")

    return load_config(write_config(mutate))
