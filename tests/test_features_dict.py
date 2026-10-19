from __future__ import annotations

import pytest

from breakout import features_dict as fd


def test_shipped_dictionary_is_valid() -> None:
    feats = fd.load()
    assert len(feats) >= 60
    assert {e["tier"] for e in feats.values()} == {"A", "B", "C"}
    # the merge features read the PR merged flag, which live payloads do not carry
    assert feats["prs_merged_28d"]["live_available"] is False
    assert "prs_merged_28d" not in fd.live_features(feats)


def _entry(**kw):
    base = {"tier": "A", "description": "x", "requires": [], "live_available": True}
    base.update(kw)
    return base


def test_live_available_is_mandatory_and_boolean() -> None:
    with pytest.raises(fd.FeatureDictionaryError, match="live_available"):
        fd.validate({"features": {"f": {"tier": "A", "description": "x"}}})
    with pytest.raises(fd.FeatureDictionaryError, match="live_available"):
        fd.validate({"features": {"f": _entry(live_available="yes")}})


def test_cannot_be_live_if_it_reads_a_null_in_live_column() -> None:
    bad = _entry(requires=[{"type": "PullRequestEvent", "column": "pr_merged"}])
    with pytest.raises(fd.FeatureDictionaryError, match="NULL in live payloads"):
        fd.validate({"features": {"merge_rate": bad}})
    ok = _entry(
        requires=[{"type": "PullRequestEvent", "column": "pr_merged"}], live_available=False
    )
    assert fd.validate({"features": {"merge_rate": ok}})


def test_live_features_lists_only_live_available() -> None:
    feats = fd.validate(
        {"features": {"a": _entry(), "b": _entry(live_available=False), "c": _entry()}}
    )
    assert fd.live_features(feats) == ["a", "c"]


def _full(**kw):
    base = _entry(
        group="g",
        dtype="int",
        unit="u",
        allowed=True,
        leakage_notes="n",
        explain_template={"high": "h", "low": "l"},
    )
    base.update(kw)
    return base


def test_strict_mode_requires_phase7_fields() -> None:
    assert fd.validate({"features": {"f": _full()}}, strict=True)
    with pytest.raises(fd.FeatureDictionaryError, match="leakage_notes"):
        fd.validate({"features": {"f": _entry()}}, strict=True)
    with pytest.raises(fd.FeatureDictionaryError, match="explain_template"):
        fd.validate({"features": {"f": _full(explain_template={"high": "h"})}}, strict=True)
    with pytest.raises(fd.FeatureDictionaryError, match="dtype"):
        fd.validate({"features": {"f": _full(dtype="str")}}, strict=True)


def test_compare_with_columns_ignores_keys_and_reports_both_directions() -> None:
    feats = {"a": _full(), "b": _full()}
    assert fd.compare_with_columns(feats, ["bucket", "repo_id", "snapshot_date", "a", "b"]) == (
        [],
        [],
    )
    assert fd.compare_with_columns(feats, ["repo_id", "a", "c"]) == (["c"], ["b"])


def test_model_features_respects_allowed_and_live() -> None:
    feats = fd.validate(
        {"features": {"a": _full(), "b": _full(live_available=False), "c": _full(allowed=False)}}
    )
    assert fd.model_features(feats) == ["a"]
    assert fd.model_features(feats, live_only=False) == ["a", "b"]
