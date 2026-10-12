# Phase 00 — Bootstrap & guardrails

## Goal
Create a clean, tested Python project skeleton with the CLI, config loader, logging, paths,
CI, and the guardrails (gitignore, secret scanning, pre-commit) that every later phase relies on.
No data work yet.

## Prerequisites
- `docs/HUMAN_SETUP.md` steps 1–5 done (repo exists, is public, `.env` exists locally).
- `CLAUDE.md`, `config/project.yaml`, `docs/` are committed.

## Deliverables
1. `pyproject.toml` managed by `uv`:
   - `requires-python = ">=3.12,<3.13"`
   - `[project.scripts] breakout = "breakout.cli:app"`
   - src layout: package at `src/breakout/`
   - Runtime deps (add now, latest stable): `duckdb`, `pyarrow`, `typer`, `pyyaml`,
     `python-dotenv`, `httpx`, `tenacity`, `huggingface_hub`, `pydantic` (v2), `rich`.
   - Dev deps (dependency group `dev`): `pytest`, `pytest-cov`, `ruff`, `mypy`, `types-PyYAML`,
     `pre-commit`.
   - Later phases add: `google-cloud-bigquery`, `google-cloud-bigquery-storage`, `dbt-core`,
     `dbt-duckdb`, `lightgbm`, `scikit-learn`, `shap`, `matplotlib`, `pandas`, `numpy`.
     Do **not** add them now.
2. `src/breakout/__init__.py` with `__version__`.
3. `src/breakout/config.py`:
   - Loads `config/project.yaml`, expands `${VAR}` from environment (after `load_dotenv()`),
     validates into pydantic models (one model per top-level section, names mirror the YAML).
   - Missing env var → keep `None` and only raise when that value is actually accessed by code
     that needs it (e.g. `cfg.huggingface.require_events_repo()`), so tests run without secrets.
   - `get_config()` is cached (`functools.lru_cache`). Accept an override path for tests.
4. `src/breakout/paths.py`: repo root detection (walk up to the dir containing `CLAUDE.md`),
   `DATA_DIR = root/"data"`, `LAKE_DIR`, `MANIFEST_DIR = DATA_DIR/"manifests"`,
   `WAREHOUSE = DATA_DIR/"warehouse.duckdb"`. Create dirs lazily via a helper `ensure_dir()`.
5. `src/breakout/logging.py`: `get_logger(name)` using `rich` handler locally and plain
   timestamped lines when `CI=true`. Level from `LOG_LEVEL` env (default INFO).
6. `src/breakout/cli.py`: Typer app with subcommand groups created as stubs that print
   "not implemented yet (Phase N)": `ingest`, `backfill`, `lake`, `enrich`, `build`, `ml`,
   `daily`, `publish`, `ops`. Plus a working `breakout info` that prints config summary
   (with secrets masked: show only whether set) and resolved paths.
7. `src/breakout/duck.py`: `connect(path=None, read_only=False)` returns a DuckDB connection
   with sensible pragmas: `SET threads TO <cpu count>`, `SET memory_limit` to 70% of RAM
   (detect with `os.sysconf` or `psutil` — if you add psutil, add it to deps),
   `SET preserve_insertion_order=false`, `SET temp_directory` under `data/tmp`.
   Install/load `httpfs` lazily only when a remote path is used.
8. `.gitignore` exactly covering CLAUDE.md §7 list.
9. `.env.example` listing: `HF_TOKEN`, `HF_USER`, `GH_ENRICH_TOKEN`, `GCP_PROJECT_ID`,
   `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD`, `LOG_LEVEL` — names only.
10. `.pre-commit-config.yaml`: ruff (lint+format), end-of-file-fixer, trailing-whitespace,
    check-added-large-files (`--maxkb=2000`), detect-private-key, and **gitleaks** for secrets.
11. `Makefile` targets: `setup` (uv sync + pre-commit install), `lint`, `fmt`, `test`, `info`.
    Each target is one line calling `uv run ...`.
12. `.github/workflows/ci.yml`: on push/PR to main: checkout, `astral-sh/setup-uv`,
    `uv sync --all-groups --frozen`, ruff check, ruff format --check, mypy src, pytest.
    `permissions: contents: read`. Use `concurrency` to cancel superseded runs on PRs.
13. `tests/test_config.py`, `tests/test_paths.py`, `tests/test_cli.py` (uses `typer.testing.CliRunner`
    to run `breakout info` with a temp config and no env vars).
14. `README.md`: a short placeholder (project one-liner, "work in progress", link to docs/ARCHITECTURE.md).
    Phase 13 rewrites it.

## Step-by-step
1. `uv init --package --name breakout` (or create files by hand if `uv init` layout differs) and
   move to `src/` layout. Ensure `uv run breakout --help` works.
2. Write config models. The YAML has `null` values (e.g. `history.cutover_date`) — model them as
   `Optional[date]`. Dates parse to `datetime.date`.
3. Write paths, logging, duck helpers.
4. Write CLI with stubs and `info`.
5. Write tests; run `uv run pytest -q`.
6. Add pre-commit, run `uv run pre-commit run --all-files`, fix issues.
7. Add CI workflow. Push and confirm CI is green (ask the human to check the Actions tab if you
   cannot see it; with `gh` CLI available, use `gh run list`).

## Rules / gotchas
- Do not add data-related code yet.
- Never print secret values, even partially. `info` prints `HF_TOKEN: set` / `not set`.
- Keep `config.py` the only place that reads `project.yaml`.

## Acceptance criteria
- [ ] `uv run breakout --help` lists all subcommand groups.
- [ ] `uv run breakout info` works with an empty environment and masks secrets.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q` all pass.
- [ ] `git status` is clean after running everything (no stray data/cache files tracked).
- [ ] CI workflow passes on GitHub.
- [ ] `docs/PROGRESS.md` updated.
