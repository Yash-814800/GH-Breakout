# Human setup checklist (do these yourself — Claude Code cannot)

None of these need a credit card. Do steps 1–5 before Phase 0, step 6 before Phase 2,
step 7 before Phase 4, step 8 before Phase 10, step 9 only if you enable the Bluesky bot.

## 1. Local machine

- Laptop with **≥ 16 GB RAM** and **≥ 150 GB free disk** for the one-time history build
  (you can lower `history.start_date` coverage if you have less — see Phase 2).
- Install: `git`, `uv` (https://docs.astral.sh/uv/), Node.js LTS (for the site),
  the Google Cloud CLI `gcloud` (for BigQuery auth), and Claude Code.

## 2. GitHub repository

1. Create a **public** repository, e.g. `gh-breakout`. (Public = free unlimited Actions
   minutes on standard runners and free GitHub Pages.)
2. Copy this prompt pack into it (`CLAUDE.md`, `config/`, `docs/`) and push.
3. Settings → Actions → General → Workflow permissions: **Read and write permissions**.
4. Settings → Pages → Build and deployment → Source: **GitHub Actions**.

## 3. Hugging Face

1. Create a free account at https://huggingface.co (no card).
2. Settings → Access Tokens → create a token with **write** access. Name it `gh-breakout`.
3. You do not need to create repos by hand; Phase 3 creates them via the API.

## 4. GitHub token for metadata enrichment

Create a **classic personal access token with no scopes ticked** (Settings → Developer settings →
Personal access tokens → Tokens (classic)). With no scopes it can only read public data, and it gives
5,000 REST requests/hour plus GraphQL.

Do **not** use a fine-grained token with "Public repositories (read-only)": measured on 2026-10-12,
such a token gets HTTP 403 "Resource not accessible by personal access token" on
`GET /repos/{owner}/{repo}/stargazers` (REST) and on `stargazers` in GraphQL, which the capture-rate
validation and the daily star cross-check (ADR-009) need. Search, repo metadata and forks do work with it.
Inside GitHub Actions, the automatic `GITHUB_TOKEN` can also list stargazers of public repos
(1,000 requests/hour/repo), so the daily cross-check does not need a PAT secret.

## 5. Secrets and local `.env`

GitHub repo → Settings → Secrets and variables → Actions:

| Name | Kind | Value |
|---|---|---|
| `HF_TOKEN` | secret | Hugging Face write token |
| `HF_USER` | variable | your HF username |
| `GH_ENRICH_TOKEN` | secret | the fine-grained PAT from step 4 |
| `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` | secret | only if using the bot (step 9) |

Locally, create `.env` (git-ignored) with the same names plus `GCP_PROJECT_ID`.

## 6. Google Cloud BigQuery sandbox (Phase 2)

1. Go to https://console.cloud.google.com/bigquery with a Google account. Create a new
   project (e.g. `gh-breakout-backfill`). **Do not add a billing account.** You should see
   a "Sandbox" notice. Put the project ID in `.env` as `GCP_PROJECT_ID`.
2. Enable the "BigQuery API" and "BigQuery Storage API" for the project (APIs & Services).
3. On your laptop: `gcloud auth application-default login` and
   `gcloud config set project <PROJECT_ID>`. The backfill script uses these
   Application Default Credentials. Nothing BigQuery-related ever goes into GitHub.
4. The sandbox gives 1 TB of scanned data per calendar month. If the backfill needs more,
   it pauses and resumes next month automatically from its manifest.

## 7. Nothing extra for Phase 4 enrichment

Uses `GH_ENRICH_TOKEN` (and no key for the Hacker News Algolia API).

## 8. Site

GitHub Pages is enabled in step 2. If you prefer Vercel (Hobby plan, no card) or
Cloudflare Pages (free, no card), Phase 10 documents the switch.

## 9. Optional Bluesky bot

Create a Bluesky account for the bot, then Settings → Privacy and security → App
passwords → create one. Save handle + app password as secrets. Set
`optional.bluesky_enabled: true` in `config/project.yaml`.
