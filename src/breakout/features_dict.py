"""Loader and validator for ``config/feature_dictionary.yaml`` (ADR-010).

Every feature declares ``live_available``. A feature that reads a column which is NULL in the live
source's payloads cannot be marked live-available; the live champion trains only on
``live_available`` features, the full-feature model is a research result.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from breakout.paths import ROOT

FEATURE_DICTIONARY_PATH = ROOT / "config" / "feature_dictionary.yaml"

# (event_type, column) pairs that are NULL for every row in post-2025-10-07 payloads
# (docs/schema_audit.md, "Parser decisions"): PR/review author and creation time, merged flag.
LIVE_NULL_FIELDS: frozenset[tuple[str, str]] = frozenset(
    {
        ("PullRequestEvent", "target_user_id"),
        ("PullRequestEvent", "target_created_at"),
        ("PullRequestEvent", "pr_merged"),
        ("PullRequestReviewEvent", "target_user_id"),
        ("PullRequestReviewEvent", "target_created_at"),
    }
)
TIERS = {"A", "B", "C"}
# Fields every shipped entry carries (Phase 7, 7.3); the minimal ones above are always checked.
FULL_FIELDS = ("group", "dtype", "unit", "allowed", "leakage_notes", "explain_template")
DTYPES = {"int", "float", "bool", "category"}
# Key / build columns of mart_repo_features that are not features
MART_KEY_COLUMNS = ("bucket", "repo_id", "snapshot_date")


class FeatureDictionaryError(ValueError):
    pass


def validate(doc: dict[str, Any], strict: bool = False) -> dict[str, dict[str, Any]]:
    feats = doc.get("features")
    if not isinstance(feats, dict):
        raise FeatureDictionaryError("`features` must be a mapping")
    errors: list[str] = []
    for name, entry in feats.items():
        if not isinstance(entry, dict):
            errors.append(f"{name}: entry must be a mapping")
            continue
        live = entry.get("live_available")
        if not isinstance(live, bool):
            errors.append(f"{name}: `live_available` must be true or false")
        if entry.get("tier") not in TIERS:
            errors.append(f"{name}: `tier` must be one of {sorted(TIERS)}")
        if not entry.get("description"):
            errors.append(f"{name}: missing `description`")
        if strict:
            for field in FULL_FIELDS:
                if field not in entry:
                    errors.append(f"{name}: missing `{field}`")
            if entry.get("dtype") not in DTYPES:
                errors.append(f"{name}: `dtype` must be one of {sorted(DTYPES)}")
            if not isinstance(entry.get("allowed"), bool):
                errors.append(f"{name}: `allowed` must be true or false")
            tpl = entry.get("explain_template")
            if not (isinstance(tpl, dict) and tpl.get("high") and tpl.get("low")):
                errors.append(f"{name}: `explain_template` needs `high` and `low` phrases")
        requires = entry.get("requires", [])
        if not isinstance(requires, list):
            errors.append(f"{name}: `requires` must be a list")
            continue
        if live is True:
            for r in requires:
                key = (r.get("type"), r.get("column"))
                if key in LIVE_NULL_FIELDS:
                    errors.append(
                        f"{name}: live_available is true but requires {key[0]}.{key[1]}, "
                        "which is NULL in live payloads"
                    )
    if errors:
        raise FeatureDictionaryError("; ".join(errors))
    return feats


def load(path: Path = FEATURE_DICTIONARY_PATH) -> dict[str, dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        return validate(yaml.safe_load(fh) or {}, strict=True)


def live_features(feats: dict[str, dict[str, Any]]) -> list[str]:
    """Names the live champion may train on."""
    return sorted(n for n, e in feats.items() if e["live_available"])


def dictionary_hash(path: Path = FEATURE_DICTIONARY_PATH) -> str:
    """SHA-256 of the dictionary file (recorded in the training manifest)."""
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_with_columns(
    feats: dict[str, dict[str, Any]], columns: list[str]
) -> tuple[list[str], list[str]]:
    """(columns missing from the dictionary, dictionary features missing from ``columns``).

    The key / build columns of the mart are not features and are ignored.
    """
    cols = {c for c in columns if c not in MART_KEY_COLUMNS}
    return sorted(cols - set(feats)), sorted(set(feats) - cols)


def model_features(feats: dict[str, dict[str, Any]], live_only: bool = True) -> list[str]:
    """Allowed features, optionally only the live-available ones (the live champion's set)."""
    return sorted(
        n for n, e in feats.items() if e["allowed"] and (e["live_available"] or not live_only)
    )
