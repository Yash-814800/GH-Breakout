"""Repository paths. The repo root is the nearest ancestor directory containing CLAUDE.md."""

from __future__ import annotations

from pathlib import Path

ROOT_MARKER = "CLAUDE.md"


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from ``start`` (default: this file) to the directory containing CLAUDE.md."""
    here = (start or Path(__file__)).resolve()
    for candidate in (here, *here.parents):
        if candidate.is_dir() and (candidate / ROOT_MARKER).is_file():
            return candidate
    raise FileNotFoundError(f"No {ROOT_MARKER} found in or above {here}")


ROOT = find_repo_root()
CONFIG_PATH = ROOT / "config" / "project.yaml"
DATA_DIR = ROOT / "data"
LAKE_DIR = DATA_DIR / "lake"
MANIFEST_DIR = DATA_DIR / "manifests"
TMP_DIR = DATA_DIR / "tmp"
WAREHOUSE = DATA_DIR / "warehouse.duckdb"


def ensure_dir(path: Path) -> Path:
    """Create ``path`` (and parents) if missing and return it. Never called at import time."""
    path.mkdir(parents=True, exist_ok=True)
    return path
