# How to use these phase prompts with Claude Code

## Setup once

1. Do `docs/HUMAN_SETUP.md` steps 1–5.
2. Put this whole pack at the root of your new public repo:
   `CLAUDE.md`, `config/project.yaml`, `docs/` (including this folder). Commit and push.
3. Open a terminal in the repo and start Claude Code.

## Running a phase

Use **one fresh Claude Code session per phase** (context stays focused; `CLAUDE.md` and
`docs/PROGRESS.md` carry state between sessions). Paste the kickoff prompt below, replacing `XX`
and the file name:

```text
Read CLAUDE.md, docs/PROGRESS.md, docs/DECISIONS.md, docs/ARCHITECTURE.md, and
docs/phases/PHASE_XX_<name>.md. Confirm the prerequisites for this phase are done in
docs/PROGRESS.md; if not, stop and tell me what is missing.

Then write a short implementation plan as a checklist covering every item in the phase's
"Deliverables" and "Acceptance criteria" sections, and wait for my OK.

After I approve: implement the phase completely, step by step, running the tests and
checks listed in the phase after each step. Do not skip acceptance criteria. Do not
invent APIs or fields — verify against real data or official docs. When finished, update
docs/PROGRESS.md and docs/DECISIONS.md, commit, and give me: (1) what was built,
(2) acceptance-criteria results with the actual command output summaries,
(3) anything I need to do by hand, (4) anything that deviated from the phase file and why.
```

Tips:
- Using Claude Code's plan mode for the planning step works well: review the plan, then let it run.
- If a session gets long or confused, stop it, make sure `docs/PROGRESS.md` reflects reality,
  and start a new session with the same kickoff prompt plus "Resume: steps 1–N are done".
- Long-running commands (backfill, history builds) — ask Claude Code to start them and report;
  you can run them yourself in another terminal with the exact command it gives you.

## Phase order and rough effort

| # | File | What you get | Who runs heavy jobs |
|---|---|---|---|
| 00 | PHASE_00_bootstrap.md | Repo skeleton, tooling, CI, config loader | — |
| 01 | PHASE_01_schema_and_parser.md | Payload audit across eras, slim schema, hourly parser | laptop (minutes) |
| 02 | PHASE_02_bigquery_backfill.md | Cost plan, manifest-driven backfill 2015→cutover | laptop (hours; may span months of quota) |
| 03 | PHASE_03_lake_on_hf.md | HF dataset repos, upload/sync, compaction, dataset card | laptop |
| 04 | PHASE_04_enrichment.md | Repo metadata, actor-id→account-age map, trending history, HN | laptop / Actions |
| 05 | PHASE_05_dbt_staging_intermediate.md | dbt sources, staging, intermediate, tests | laptop |
| 06 | PHASE_06_labels_baseline_eval.md | Candidate universe, labels, baseline, eval harness | laptop |
| 07 | PHASE_07_features.md | Point-in-time feature marts (Tier A/B/C), tastemaker | laptop (hours, once) |
| 08 | PHASE_08_model.md | LightGBM, rolling-origin CV, calibration, SHAP, model card | laptop |
| 09 | PHASE_09_daily_pipeline.md | Daily + weekly + health workflows in GitHub Actions | Actions |
| 10 | PHASE_10_site.md | Astro site on GitHub Pages | Actions |
| 11 | PHASE_11_fake_stars_similarity_cohorts.md | Suspicious-growth score, similar repos, cohort retention | Actions |
| 12 | PHASE_12_distribution.md | RSS, badges, weekly digest, Bluesky bot | Actions |
| 13 | PHASE_13_polish.md | README, dbt docs on site, ClickHouse benchmark post, final audit | laptop |

You will have a working end-to-end leaderboard after Phase 10. Phases 11–13 are what make it
stand out.

## Shortcut if you want results fast

Phase 2 supports a "fast start": backfill only the most recent 18 months first
(`--since 2025-04`), finish phases 3–10 on that slice, then let the backfill fill older months
over following weeks and retrain. The phase files call this out where it matters.
