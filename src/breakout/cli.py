"""Command line interface (``breakout``). Groups are stubs until their phase lands."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from breakout import __version__
from breakout import paths as P
from breakout.config import get_config

app = typer.Typer(help="gh-breakout: predict GitHub repo breakouts.", no_args_is_help=True)

ENV_VARS = (
    "HF_TOKEN",
    "HF_USER",
    "GH_ENRICH_TOKEN",
    "GCP_PROJECT_ID",
    "BLUESKY_HANDLE",
    "BLUESKY_APP_PASSWORD",
)

_STUBS = {
    "ingest": 1,
    "backfill": 2,
    "lake": 3,
    "enrich": 4,
    "build": 5,
    "ml": 6,
    "daily": 9,
    "publish": 10,
    "ops": 9,
}


def _make_stub(name: str, phase: int) -> typer.Typer:
    group = typer.Typer(help=f"{name} commands (Phase {phase}).", invoke_without_command=True)

    @group.callback()
    def _stub() -> None:
        typer.echo(f"{name}: not implemented yet (Phase {phase})")

    return group


for _name, _phase in _STUBS.items():
    app.add_typer(_make_stub(_name, _phase), name=_name)


@app.callback()
def main(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option("--config", envvar="BREAKOUT_CONFIG", help="Path to a project.yaml."),
    ] = None,
) -> None:
    ctx.obj = {"config": config}


@app.command()
def info(ctx: typer.Context) -> None:
    """Print a config summary and resolved paths. Secrets show only 'set' / 'not set'."""
    cfg = get_config(ctx.obj["config"])
    typer.echo(f"breakout {__version__}")
    typer.echo(f"project: {cfg.project.name} (timezone {cfg.project.timezone})")
    typer.echo(f"history: {cfg.history.start_date} -> cutover {cfg.history.cutover_date}")
    typer.echo(f"labels: horizon {cfg.labels.horizon_days}d, primary {cfg.labels.primary}")
    typer.echo("environment:")
    for var in ENV_VARS:
        typer.echo(f"  {var}: {'set' if os.environ.get(var) else 'not set'}")
    typer.echo(f"  LOG_LEVEL: {os.environ.get('LOG_LEVEL', 'INFO (default)')}")
    typer.echo("paths:")
    for label, value in (
        ("root", P.ROOT),
        ("config", ctx.obj["config"] or P.CONFIG_PATH),
        ("data", P.DATA_DIR),
        ("lake", P.LAKE_DIR),
        ("manifests", P.MANIFEST_DIR),
        ("warehouse", P.WAREHOUSE),
    ):
        typer.echo(f"  {label}: {value}")


if __name__ == "__main__":
    app()
