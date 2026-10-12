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


class FeatureDictionaryError(ValueError):
    pass


def validate(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
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
        return validate(yaml.safe_load(fh) or {})


def live_features(feats: dict[str, dict[str, Any]]) -> list[str]:
    """Names the live champion may train on."""
    return sorted(n for n, e in feats.items() if e["live_available"])
