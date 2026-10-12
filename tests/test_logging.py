from __future__ import annotations

from breakout.logging import get_logger


def test_namespace():
    assert get_logger("breakout.x").name == "breakout.x"
    assert get_logger("other").name == "breakout.other"
