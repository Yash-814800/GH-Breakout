"""Project logger: rich handler locally, plain timestamped lines when CI=true."""

from __future__ import annotations

import logging
import os
import sys

_ROOT_NAME = "breakout"
_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return
    root = logging.getLogger(_ROOT_NAME)
    handler: logging.Handler
    if os.environ.get("CI", "").lower() == "true":
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%dT%H:%M:%SZ"
            )
        )
    else:
        from rich.logging import RichHandler

        handler = RichHandler(rich_tracebacks=True, show_path=False)
    root.handlers[:] = [handler]
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    root.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the ``breakout`` namespace, configuring handlers on first use."""
    _configure()
    if name != _ROOT_NAME and not name.startswith(_ROOT_NAME + "."):
        name = f"{_ROOT_NAME}.{name}"
    return logging.getLogger(name)
