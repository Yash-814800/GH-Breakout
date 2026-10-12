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
