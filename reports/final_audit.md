# Final audit (Phase 13.5)

Date: 2026-10-21. Commit audited: the Phase 13 branch on top of `main` after Phase 12 (PRs #4 and #5). Every
number below was produced in this audit session; commands are given so that each can be repeated.

## Summary

| Area | Result |
|---|---|
| Security | No leaks in the full git history (75 commits); no token in the last 14 workflow logs; every workflow has minimal permissions; third-party actions pinned to SHAs; Dependabot and `SECURITY.md` added. **One finding for the human:** two tokens were echoed into the working session, rotate them (see Security) |
| Cost and limits | Everything is $0. One item to watch: Hugging Face public storage is "best effort" and the lake is 116.7 GB |
| Reproducibility | A fresh clone passes `make setup` and all tests. `daily run --no-upload` **did not work on a clean clone** (bootstrap was tied to the upload flag): **fixed**, then verified end to end (1,033 candidates, same as the live run) |
| Correctness | Leak test PASS on 2 more dates (and 2 in earlier phases); parity PASS (Jaccard 1.0000, cell match 99.9883%); ledger verified locally and against the Hub; `lake verify --remote` 0 problems |
| Code quality | ruff and mypy clean; 390 Python tests; coverage **63%** (target 70%, not met, see below); dead-code scan has 3 real candidates |
| Housekeeping | MIT `LICENSE`, `CITATION.cff`, `CONTRIBUTING.md`, bug and review-request issue templates, repository metadata suggestions below |
| Blocking findings | None open. Items for the human are listed at the end |

## Security

- **gitleaks over the full history** (`gitleaks git --log-opts="--all"`, v8.30.1): 75 commits scanned, no leaks.
- **Token prefixes in logs:** the logs of the 14 most recent workflow runs were searched for `hf_`, `ghp_`, `gho_`,
  `ghs_` and `github_pat_` followed by 20 or more characters: 0 matches in all 14.
- **Workflow permissions:** every workflow declares top-level `permissions`: `ci`, `site`, `source-test`, `backfill-day`,
  `hourly-backfill` use `contents: read` (site adds `pages`/`id-token`); `daily`, `weekly`, `monthly` need `contents: write`
  (ledger and heartbeat commits); `weekly` also has `discussions: write` (Phase 12.5); `health` has `issues: write` and
  `actions: write`; `update-visual-snapshots` has `contents` and `pull-requests: write`. The deploy job of `daily.yml` now
  also lists `contents: read` (job-level permissions replace the workflow's).
- **Third-party actions are pinned to commit SHAs** (with the tag as a comment): `actions/checkout`, `setup-node`,
  `upload-artifact`, `download-artifact`, `upload-pages-artifact`, `deploy-pages`, `astral-sh/setup-uv`,
  `peter-evans/create-pull-request`. Dependabot (`.github/dependabot.yml`) updates uv, npm (`/site`) and Actions weekly.
- `SECURITY.md` (private vulnerability reporting) and `CONTRIBUTING.md` were added.
- **FINDING (human action): two secrets were printed during this audit.** A debugging trace (`set -x`) of the
  fresh-clone script echoed the values of `HF_TOKEN` and `GH_ENRICH_TOKEN` from the local `.env` into the terminal output of
  this working session. They were never written to git or to a workflow log, and the local log file was scrubbed, but
  they are in the session transcript. Rotate both (Hugging Face: Settings, Access Tokens; GitHub: classic token, 1-year, no
  scopes; update the Actions secrets and `.env`; `docs/runbook.md`, "Credential rotation").

## Cost and limits (official documentation, read 2026-10-21)

| Service | Documented limit | Current use | Share |
|---|---|---|---|
| GitHub Actions, public repo, standard runners | "free for public repositories that use standard GitHub-hosted runners"; no minute cap stated | daily 5 to 10 min (419 s to 629 s on the last successful runs), weekly 15.5 min, CI about 10 min | not applicable |
| GitHub Pages | published site at most 1 GB; soft 100 GB/month bandwidth; deployments time out after 10 min; soft 10 builds/hour (not for Actions deployments) | `dist/` is 60 MB (14 MB of it the dbt docs) | 6% of the size limit |
| Hugging Face | free public storage is "best-effort"; "beyond the first few gigabytes, please use this resource responsibly"; recommended < 100k files per repo, < 10k entries per folder, about 100 files per commit | events 114.96 GB in 1,628 files, derived 1.76 GB (150 files), snapshots and models tiny; commits are capped at 80 files / 1.5 GB by the sync code | files: 1.6% of the recommended count; **storage: no hard limit, but see the finding below** |
| BigQuery sandbox | 1 TiB of query processing per month, 10 GiB lifetime storage, tables expire after 60 days, no billing account needed | 522.7 GB billed for the whole one-time backfill, nothing stored in BigQuery | 51% of one month's quota, once |
| GitHub REST (token) | 5,000 requests/hour; `GITHUB_TOKEN` 1,000/hour per repository | a few hundred per daily run with `GH_ENRICH_TOKEN` | below 10% |

Items within 50% of a limit: **none** with a hard limit. **FINDING:** the 116.7 GB on Hugging Face is within a
"best-effort" allowance, not a guaranteed one, and the Hub says large public datasets should show community
reuse. If it ever became a problem the lake can be thinned (the hourly era is rebuildable from GH Archive) or
the owner can apply for a storage grant; there is no billing risk because no card is attached.

Weekly job runtime trend: 15.5 min (one successful run). Daily: 7.0 min (a re-run), 10.5 min (the run of 2026-10-21
morning) and 7.1 min (the scheduled run); the median over the last six runs is about 7 min against a 90-minute timeout.

## Reproducibility

Procedure: `git clone` of the branch into a temporary directory, `make setup`, `uv run pytest -q`, then
`uv run breakout daily run --date 2026-10-20 --no-upload --no-commit` against the Hugging Face data (the
phase file's command).

| Step | Result |
|---|---|
| `make setup` | OK (uv sync of all groups, pre-commit hook installed) |
| tests | all pass (2 skipped, by design) in about 2 minutes |
| daily run, first attempt | **failed**: `--no-upload` skipped the bootstrap, so a clean checkout had no manifest, enrichment tables, state or champion and step 5 died on missing files |
| fix | `--no-upload` now only stops writes; the bootstrap still reads what is missing (idempotent). New option `--skip-bootstrap` for the old behaviour |
| daily run, second attempt | success in about 13 minutes (bootstrap pull, five dbt invocations, all models pass; scoring): 1,033 candidates, the same count as the live run of that date |
| bit-for-bit reproduction | **not met**: the regenerated predictions file differs from the frozen one, so the run reported a ledger conflict for 2026-10-20 (the frozen snapshot is immutable and is never overwritten). The candidate count agrees; the bytes do not (Parquet metadata or late-arriving source hours). A same-day re-run of `daily.yml` had the same effect and set the heartbeat to `unhealthy` (health issue #3). **Fixed after the audit:** a re-run of a frozen date now keeps the frozen snapshot and publishes from it (`adopt_frozen_snapshot`), so it is idempotent and stays healthy |

## Correctness

- **Leak test** (`breakout build leak-test --date D --sample 300`): PASS on 2024-06-03 (71 of 71 columns non-NULL)
  and 2021-03-01 (60 of 71 non-NULL, the others are Tier B, NULL before 2023-06), 300 rows each, 0 rows differing from the
  history mart. Earlier phases recorded PASS on 2018-05-14, 2021-03-01, 2024-06-03 and 2026-10-12.
- **Daily/history parity** (`breakout ops parity --date 2024-06-03`): PASS. Candidate Jaccard 1.0000 (12,434 of 12,434),
  cell match 99.9883%. Report: `docs/parity_daily_vs_history.md`.
- **Ledger:** `breakout ops verify-ledger` verified 2 entries locally and against the Hub snapshots (`--remote`).
- **Lake:** `breakout lake verify --remote`: 0 problems. Local `lake verify` lists 10 violations that are all
  `day-2024-06-03` files next to the `bq` month files: the parity test re-ingests that day locally. They are test
  leftovers, the dbt file lists drop them (ADR-010), and nothing is published from them.
- **dbt:** 52 models, 274 data tests, 500 documented columns; `dbt parse` and `dbt docs generate` pass. The
  full `dbt test` against the 33 GB warehouse was not re-run (about a day of compute); its last full result is in
  `docs/PROGRESS.md` (Phase 5 to 7, 63 and 162 tests pass) and CI runs the synthetic-world suite.
- **Site:** Vitest 41, Playwright 178 in the pinned container (layout 19 routes x 4 widths, content, accessibility in
  light and dark, 16 visual snapshots), token lint, base-path check, link check; all pass.

## Code quality

- `ruff check`, `ruff format --check` and `mypy src` (84 files) are clean. Python tests: 390 (this audit added
  distribution, dbt docs, site export and CLI tests).
- **Coverage of `src/breakout`: 63%** (9,918 statements; 3,625 missed), measured with `pytest --cov`. The aim of 70%
  was **not met**. The gap is concentrated in orchestration and report-writing modules that need the 33 GB warehouse or the
  network and are exercised by the daily, weekly and parity runs instead: `daily/run.py` 10%, `ml/cv_report.py` 17%,
  `ml/final.py` 18%, `ops/parity.py` 0%, `detect/validate.py` 0%, `cli.py` 29%. Well covered: ingest and lake (92 to
  99%), config, metrics, calibration, leak test, distribution (85%), site export (74%).
- **Dead code** (`vulture --min-confidence 80`): only the signal-handler arguments in `cli.py` (false positive). At 60%
  confidence nearly everything is pydantic fields. Real candidates: `detect.similarity.compute_cosine_similarity`,
  `duck.ensure_httpfs`, `enrich.actor_age.est_account_created_at`. Left in place (small, tested or documented).
- Findings noted while reading code, not fixed (data models cannot be rebuilt cheaply): the dbt `int_contributor_sessions`
  orders its running sum by `created_at` only, so events within the same second can be assigned to sessions in either order
  (found because the benchmark query needed `event_id` as a tiebreak to agree across engines); the live detector
  (`detect/scoring.py`) weights six signals including lockstep while the dbt history mart `mart_suspicion` uses five (its
  `s_lockstep` is constant 0); the status page counts dbt tests defined, not tests passed.

## Phases 1 to 14: is everything implemented and working?

| Phase | Check performed in this audit | Result |
|---|---|---|
| 0 Bootstrap | CI green on `main` after Phase 12 (test, site-build, site-qa); pre-commit hooks installed in a fresh clone | OK |
| 1 Schema and parser | `docs/schema_audit.md` exists; ingest tests pass; the clean-clone daily run ingested nothing new and reproduced the day | OK |
| 2 BigQuery backfill | cost plan and manifests present; `lake verify` OK; 522.7 GB billed noted against the quota | OK |
| 3 Lake on Hub | 4 public repos, 1,628 + 150 files; `lake verify --remote` 0 problems; monthly workflow green | OK |
| 4 Enrichment | 7 tables pulled by the clean clone (bootstrap) and used by the dbt builds | OK |
| 5 dbt staging and intermediate | `dbt parse` and docs generation; 52 models all with described columns; CI synthetic suite | OK (full warehouse test not re-run) |
| 6 Candidates, labels, baseline | candidates reproduced by the clean-clone run (1,033); baseline numbers in README match `reports/baseline.md` | OK |
| 7 Features | leak test PASS on 2 dates, parity PASS | OK |
| 8 Model | champion `20261019-b5ff585` loaded from the Hub by the clean clone; metrics match `reports/model_cv.md` | OK. Known limit: calibration over-predicts on non-Monday days, now disclosed on the methodology page |
| 9 Daily pipeline | daily run green on Actions (several times today) and green in a clean clone after the bootstrap fix; ledger verified; same-day re-run reports a conflict by design | OK after fix. Live enrichment of brand-new repos is partly wired (language and owner type come from the GitHub lookup at publish time) |
| 10 Website | every route returns 200 live; data files and Parquet explorer files served; `status.json` now carries rows per event type and the dbt test count (both were empty or hardcoded) | OK after fix |
| 11 Fake stars, similar repos, cohorts | tests pass; `/insights/` live; label policy still awaits the human's confirmation | OK |
| 12 Distribution | feeds, badges, digest live; see `docs/DECISIONS.md` ADR-032 | OK (Bluesky bot intentionally not built) |
| 13 Polish | this report, README, dbt docs, benchmark, blog, summary | OK |
| 14 Front end | Playwright 178 passed, Vitest 41, token lint, link check | OK |

## Housekeeping

- `LICENSE` (MIT, owner's decision), `CITATION.cff`, `CONTRIBUTING.md`, `SECURITY.md`, issue templates (bug, review request).
- Repository settings applied by the agent: homepage set to the live site, description, topics, Discussions enabled,
  private vulnerability reporting enabled. Suggested values are in the final message of the session.

## Items for the human

1. **Rotate `HF_TOKEN` and `GH_ENRICH_TOKEN`** (printed during this audit, see Security).
2. Create a Discussions category named **Digest** (Settings, Discussions); until then the weekly digest posts to Announcements.
3. Confirm the label policy after the suspicion ablation (Phase 11, still open) and decide on the over-prediction on
   non-Monday days (retrain and calibrate on daily snapshots, or keep the disclosure).
4. Watch Hugging Face storage guidance (best-effort public storage, 116.7 GB).
5. Dependabot will open its first pull requests; the Playwright snapshot workflow needs "Allow Actions to create pull
   requests" if you want to use it.
