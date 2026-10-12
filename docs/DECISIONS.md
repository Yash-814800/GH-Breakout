# Decision log (ADR-style)

Append new decisions at the bottom. Never rewrite old ones; supersede them with a new entry.
Format: `## ADR-NNN: Title (YYYY-MM-DD)` then **Context**, **Decision**, **Consequences**.

## ADR-001: Zero-cost, no-card infrastructure (2026-10-12)
**Context:** The project must run for $0 with no credit card on any service.
**Decision:** GitHub (public repo, Actions, Pages, Releases), Hugging Face public datasets/models,
BigQuery sandbox for the one-time backfill only (run from the laptop), DuckDB + dbt for compute.
**Consequences:** No Cloudflare R2/S3. Lake storage must stay modest (target < 60 GB total) and the
dataset must be documented as a reusable public dataset. HF browser CORS limits mean the site serves its
own Parquet for DuckDB-WASM.

## ADR-002: Hybrid backfill — BigQuery spine for all history, payload detail budget-limited (2026-10-12)
**Context:** BigQuery bills by bytes of the columns scanned. The JSON `payload` column is most of the
bytes; scanning it for 2015→2026 would take several months of the free 1 TB quota.
**Decision:** Extract spine columns for all months (cheap). Extract payload-derived detail columns
newest-first while the monthly budget allows, in the same query as the spine for that month so payload is
scanned once. Record coverage in a manifest; resume next month. Optionally fill older detail from hourly
files on the laptop.
**Consequences:** Features are tiered. `history.detail_start_date` marks where Tier B features begin.

## ADR-003: Events API payload trimming on 2025-10-07 (2026-10-12)
**Context:** GitHub removed push commit lists/counts, many pull-request fields, and `author_association`.
**Decision:** Phase 1 audits payload keys per era. Features never rely on `author_association`;
"maintainer"/"first-time contributor" are computed from our own history. PR merge features use whatever
the audit shows is still present, with explicit era flags.
**Consequences:** Some Tier B features change definition across the cutoff; models include an
`era_post_2025_10` indicator and the evaluation reports post-cutoff performance separately.

## ADR-004: GitHub Pages + Astro for the site (2026-10-12)
**Context:** Need a free static host; data refreshed daily.
**Decision:** Astro static build, deployed from the daily workflow with `actions/deploy-pages`.
Vercel Hobby / Cloudflare Pages documented as alternatives.
**Consequences:** Site must respect the GitHub Pages project base path (`/<repo>/`).

## ADR-005: Timestamps are naive UTC `TIMESTAMP` (2026-10-12)
**Context:** CLAUDE.md section 5 requires choosing once between `TIMESTAMP` and `TIMESTAMPTZ`.
**Decision:** Store all event and snapshot times as naive `TIMESTAMP` that is documented as UTC; dates as `DATE`.
`project.timezone` is `UTC` in config.
**Consequences:** No timezone conversion anywhere in SQL or Python. Any ingest code must convert
tz-aware inputs to UTC and drop the tzinfo before writing.

## ADR-006: Config loading rules (2026-10-12)
**Context:** Tests and tooling must run without secrets, and the real `.env` must not leak into tests.
**Decision:** `breakout.config` is the only reader of `project.yaml`; it validates with pydantic
(`extra="forbid"`, so typos fail loudly). A `${VAR}` string with any unset variable becomes `None`;
`require_*` accessors raise only on use. `.env` is loaded only when the default config path is used,
never when an explicit path or `--config` / `BREAKOUT_CONFIG` is given. `training.embargo_days >=
labels.horizon_days` is enforced at load time.
**Consequences:** New YAML keys require a matching model field in the same change.
