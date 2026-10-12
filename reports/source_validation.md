# Source validation: OpenDigger vs GH Archive vs the stargazers API

**Status: NOT COMPLETE. The go/no-go for switching to OpenDigger is "no-go until the items below are
resolved". `ingest.sources[opendigger].enabled` stays `false`.**

Date of measurements: 2026-10-12.

## What the plan asked for

~200 repos with 20-500 stars gained in Sep 2026; stargazers with timestamps from the GitHub API;
capture % per repo against (a) OpenDigger and (b) GH Archive for 2026-09-06..now, and against GH
Archive in a healthy month (2024-03). Proceed only if OpenDigger is close to the 2024 GH Archive level.

## What could not be done, and why

| Step | Result |
|---|---|
| Stargazer timestamps (ground truth) | **Blocked.** `GH_ENRICH_TOKEN` is a fine-grained "public repositories, read-only" PAT. `GET /repos/{o}/{r}/stargazers`, `GET /repositories/{id}/stargazers` and GraphQL `stargazers` all return 403 "Resource not accessible by personal access token" (even for `octocat/Hello-World`). Search, repo metadata and forks work. A classic no-scope PAT (or `GITHUB_TOKEN` in Actions) is needed; account action, left to the human. The client and repo selection are ready (`breakout.enrich.stargazers`). |
| OpenDigger WatchEvents for 2026-09-06..now | **Not feasible from the dev machine.** Files are 214-446 MB per hour; measured download rate was 5.7-7.0 KB/s (5 MB range: 229 KB in 40 s; 128 KB index page: 12.8 s) against 4.5 MB/s for data.gharchive.org. One hour would take ~18 h. Six parallel full-hour downloads and eight 1.5 MB ranged samples all failed to complete within ~25 min. |
| OpenDigger manifests (`...-H.manifest.json`) | **404 for every hour probed** (2026-09-06 hours 0, 1, 2, 12, 23; 2026-09-12-10, 09-20-5, 09-30-18, 10-05-9, 10-11-12/20), although announced in igrigorik/gharchive.org#323. Integrity and gap detection cannot use them yet. |
| Ranged head-of-file samples from data.gharchive.org (2026-09-08..10-11, 8 hours) | Not usable as a rate: the first 3 MB of an hourly file is not time-ordered by type (PushEvent 69-91 % of the head, WatchEvent 0.18-1.04 % except one 2.4k-event sample), so mix and per-minute rates are biased. Discarded. |

## What is established without the API

Source of truth for these numbers: `reports/capture_quality.md` (BigQuery day tables = GH Archive
as served by gharchive.org; WatchEvent per day divided by the median of the same weekday in 2024).

| window | stars vs 2024 baseline |
|---|---|
| 2025-05-18..23 | 0.90-0.99 |
| 2025-05-24..31 | 0.60-0.73 (abrupt onset on 2025-05-24) |
| 2025-06..09 monthly median | 0.58-0.66 |
| 2025-10..2026-01 | 0.44-0.46 |
| 2026-02..04 | 0.30-0.37 |
| 2026-05 / 06 / 07 / 08 | 0.12 / 0.05 / 0.01 / 0.01 |
| 2026-09-04..06 | 0.48 / 0.69 / 0.74 (partial recovery), then 0.03-0.53 and mostly < 0.1 |
| 2026-10-01..11 | 0.03-0.09 |

All other event types in that stream stay near baseline (all-events ratio 0.68-0.76), so this is a
star-capture failure of the gharchive.org collector, as reported in igrigorik/gharchive.org#320.

Upstream measurements against the stargazers API (from #320, two repos, not ours): capture 85-98 %
through 2025-05, 52-71 % in 2025-07..08, 15-21 % in 2026-02, 0-14 % in 2026-04/05.

## To finish (needs a human)

1. Provide a classic no-scope PAT (or approve using `gh auth token` locally for read-only public calls).
2. Decide how OpenDigger will be reached at a usable speed (it is ~6 KB/s from here): test from a
   GitHub Actions runner, or fetch with ranged/parallel requests, before it can be a daily source.
3. Then run: select ~200 repos (search `created:` windows, stars 20-500 in Sep 2026), pull stargazers
   with `starred_at`, and compare per-repo capture on a sample of OpenDigger and GH Archive hours;
   repeat for 2024-03 against BigQuery `githubarchive.month.202403`. Report p10/p25/median/p75 of
   per-repo capture.
