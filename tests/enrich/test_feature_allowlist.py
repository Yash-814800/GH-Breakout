from __future__ import annotations

import yaml

from breakout import features_dict
from breakout.enrich import github_meta
from breakout.features_dict import FEATURE_DICTIONARY_PATH

NEVER = {
    "stargazer_count_at_fetch",
    "description",
    "topics",
    "homepage_url",
    "is_archived",
    "is_mirror",
    "is_template",
    "license_spdx",
}


def _doc() -> dict:
    return yaml.safe_load(FEATURE_DICTIONARY_PATH.read_text(encoding="utf-8"))


def test_dictionary_still_validates() -> None:
    features_dict.validate(_doc())


def test_metadata_allow_list_is_exactly_the_documented_exceptions() -> None:
    cols = _doc()["enrichment_columns"]["repo_metadata"]
    allowed = {c for c, v in cols.items() if v["model_feature"]}
    assert allowed == {"created_at", "is_fork", "primary_language", "owner_type"}
    assert NEVER.isdisjoint(allowed)
    # every parquet column is classified, and nothing classified is missing from the parquet
    assert set(cols) == set(github_meta.SCHEMA.names)
    for name in ("primary_language", "owner_type"):
        assert cols[name]["adr"] == "ADR-017"
