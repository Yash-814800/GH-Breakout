# Contributing

Thanks for looking. This is a portfolio project that runs on free services, so a few rules matter more
than usual. The full contract for working in the repository is `CLAUDE.md`.

## Setup

```bash
make setup        # uv sync + pre-commit
make lint         # ruff, ruff format --check, mypy
make test         # pytest
```

Python 3.12 and [uv](https://docs.astral.sh/uv/) are required; Node 22 for the site (`cd site && npm ci`).
You need no credentials to run the tests or to build the site on the fixture data in `site/test-data/`.

## Rules that are not negotiable

1. **$0, no card.** No new paid or card-gated service.
2. **No secrets and no data files in git.** Data goes to Hugging Face; see section 7 of `CLAUDE.md` for the
   few small files that are allowed.
3. **Never key on a repository name.** Use `repo_id` (names are display-only).
4. **No future data in features, no random train/test splits.** Features for a snapshot `D` use events before
   `D` only; evaluation is rolling-origin with an embargo.
5. Every new module has unit tests, and every new dbt model has a description and tests on its grain.

## Pull requests

- Small, with a [conventional commit](https://www.conventionalcommits.org/) title (`feat(ingest): ...`).
- `uv run ruff check . && uv run ruff format --check . && uv run pytest -q` must pass; site changes also
  need `cd site && npm test && npm run build:fx && npx playwright test`.
- Record design decisions in `docs/DECISIONS.md` (context, decision, consequences).

## Opting a repository out

Open an issue with the "Request Star Pattern Review" template, or ask for removal; hidden repositories are
listed in `config/hidden_repos.yaml`.
