# Runbook

Operational procedures. Keep each section short and actionable.

## Credential rotation

| Secret | Where | Kind | Expiry | Rotate by |
|---|---|---|---|---|
| `GH_ENRICH_TOKEN` | local `.env` and GitHub Actions secret | classic PAT, **no scopes** (public data only) | 1 year from creation | see below |
| `HF_TOKEN` | local `.env` and GitHub Actions secret | Hugging Face write token | none (revoke manually) | rotate yearly |

**GitHub PAT rotation reminder.** The `GH_ENRICH_TOKEN` classic PAT was created on 2026-10-12 with a
1-year expiry, so it stops working on **2027-10-12**. Put a calendar reminder for 2027-09-28
(two weeks before). To rotate:

1. GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate
   new token. Tick **no scopes**; expiry 1 year; note `gh-breakout enrich YYYY-MM`.
2. Update `.env` locally (`GH_ENRICH_TOKEN=`) and the repository secret
   (Settings → Secrets and variables → Actions → `GH_ENRICH_TOKEN`).
3. Verify: `uv run breakout info` reports `GH_ENRICH_TOKEN: set`, then run any enrich command.
4. Delete the old token. If a token was ever pasted into a chat or log, rotate it immediately.

The daily workflow uses this PAT, not the automatic `GITHUB_TOKEN` (1,000 requests/hour is too low
for the enrichment budget).

> Note (2026-10-12): GitHub restricted the stargazers listing endpoints to repository admins and
> collaborators in July 2026 (changelog 2026-06-30). With a no-scope PAT, `/repos/{o}/{r}/stargazers`
> returns 404 and GraphQL `stargazers` returns an empty list for repositories we do not own.
> `stargazerCount`, search, repo metadata and `/users/{u}/starred` still work. See ADR-010.

## Lake on Hugging Face (Phase 3)

Repos (all public, created by `breakout lake init`; names from `config/project.yaml`):
`gh-breakout-events` (events, push_daily, manifests, `catalog.parquet`, README),
`gh-breakout-derived`, `gh-breakout-snapshots` (**never delete, squash or rewrite**),
`gh-breakout-models` (model repo). `HF_USER` must be set in `.env` and as the Actions variable
`HF_USER`; `HF_TOKEN` is an Actions secret.

**Where bytes go.** `data/` is a symlink to the Lexar SSD, and the Hugging Face cache
(`HF_HOME`) defaults to `data/hf_home` on the same disk, so nothing large lands on `/home`. All
lake commands refuse to run if the lake root is missing (SSD unmounted).

| Task | Command |
|---|---|
| Create repos / refresh cards | `uv run breakout lake init` |
| See what would be uploaded | `uv run breakout lake push --dry` |
| Upload history (resumable) | `systemd-run --user --scope -p MemoryMax=3G -p MemorySwapMax=0 uv run breakout lake push --table all` (run in the background, log to a file) |
| Upload a slice | `... lake push --since 2023-01 --until 2023-05` |
| Selective download | `uv run breakout lake pull --types WatchEvent --since 2024-01-01 --until 2024-03-31 [--push-daily] [--to DIR] [--manifests]` |
| Compact a finished month | `uv run breakout lake compact --month 2024-06` (one atomic commit: month files + catalog, day files deleted) |
| Local catalog totals | `uv run breakout lake catalog` |
| Verify | `uv run breakout lake verify [--deep] [--remote]` |
| Backfill one hourly month (Actions job body) | `uv run breakout lake backfill-month 2024-06 --workers 3` |

**Resumability.** A push skips files whose sha256 already matches the remote catalog; every commit
carries the updated `catalog.parquet` and is guarded by `parent_commit`, so an interrupted or
raced upload simply continues. At most `huggingface.max_files_per_commit` files and
`max_bytes_per_commit` bytes go into one commit. A month with `month-` files on the Hub is skipped
by `backfill-month`. Delete nothing locally until `lake verify --remote` is clean.

**Hourly-era backfill.** Run the `hourly-backfill` workflow (Actions -> Run workflow). It plans one
matrix job per month from `history.cutover_date`, ingests, compacts, pushes and writes a manifest
fragment `manifests/hourly/hourly-YYYYMM.parquet` (merged locally by `lake pull --manifests`). It
can be re-run safely; finished months are skipped.

**Squash policy.** The events repo accumulates 1-2 commits a day. After human approval a yearly
`HfApi.super_squash_history` on the **events** repo is allowed (the catalog and git ledger remain
the audit trail). Never squash `gh-breakout-snapshots`; `hf.PROTECTED_REPOS` blocks deletes there.

**If Hugging Face throttles or refuses.** Keep `bq` history in the repo and publish the hourly era
as month files only (ADR-014 item 5); tell the human before deleting anything remotely.
