from __future__ import annotations

import pytest

from breakout import features_dict as fd


def test_shipped_dictionary_is_valid() -> None:
    assert fd.load() == {}  # populated in Phase 7; the file must already validate


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
