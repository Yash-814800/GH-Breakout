# Source validation: OpenDigger vs data.gharchive.org from a GitHub Actions runner

**Verdict: NO-GO for OpenDigger as a live source.** It fails the throughput criterion by about two
orders of magnitude, its manifests do not exist, and the star-capture criterion cannot be measured the
way it was specified because GitHub removed public stargazer lists (see below).
`ingest.sources[opendigger].enabled` stays `false`; `live.source` stays `null`.

- Workflow: `.github/workflows/source-test.yml` (`workflow_dispatch`), run
  [38194688025](https://github.com/Yash-814800/GH-Breakout/actions/runs/38194688025), 2026-10-12
  02:09-02:56 UTC.
- Runner: `ubuntu-latest`, Linux 6.17.0-1022-azure x86_64, **US / Arizona, AS8075 Microsoft**.
- Hours tested (the 3 most recent complete hours, UTC): 2026-10-11 21:00, 22:00, 23:00.
- Script: `scripts/source_test.py` (stdlib only; 15-minute cap per file).

## 1. Throughput

| hour | source | file size | downloaded | seconds | sustained MB/s | time to first byte |
|---|---|---:|---:|---:|---:|---:|
| 2026-10-11-21 | opendigger | 440.2 MB | 7.3 MB (1.7 %) | 906.8 (cap) | **0.008** | 146.8 s |
| 2026-10-11-22 | opendigger | 424.9 MB | 8.4 MB (2.0 %) | 916.9 (cap) | **0.010** | 119.2 s |
| 2026-10-11-23 | opendigger | 367.0 MB | 9.4 MB (2.6 %) | 932.2 (cap) | **0.011** | 108.3 s |
| 2026-10-11-21 | gharchive | 14.9 MB | complete | 0.4 | **54.8** | 0.1 s |
| 2026-10-11-22 | gharchive | 14.9 MB | complete | 0.4 | **54.2** | 0.1 s |
| 2026-10-11-23 | gharchive | 14.7 MB | complete | 0.4 | **54.1** | 0.1 s |

GO criterion "sustained >= 1 MB/s from the runner": **FAIL** (0.008-0.011 MB/s, i.e. ~10 KB/s; a
single 400 MB hour would take over 11 hours, a day about 11 days). The developer machine measured
5.7-7.0 KB/s earlier the same day, so the slowness is the host or its route, not our network.

## 2. Manifests

| check | opendigger | gharchive |
|---|---|---|
| `...-H.manifest.json` for the 3 tested hours | 404, 404, 404 | 404, 404, 404 |
| same manifest URL over the last 48 complete hours (HEAD) | 0 found / 48 | 0 found / 48 (not expected) |

The per-hour manifests announced in igrigorik/gharchive.org#323 do not exist (also 404 on
2026-10-12 earlier for 2026-09-06 hours 0, 1, 2, 12, 23 and five later hours). Integrity and gap
checks against them are impossible; `ingest.sources[].manifest_keys` stays null.

## 3. Event counts by type (the 3 hours)

OpenDigger files were not fully received (<= 2.6 % each), so their counts are **partial and not a
rate**: the head of an OpenDigger file is not a random sample of the hour. Full-hour counts exist
only for gharchive.

| hour | source | lines | Watch | Fork | Issues | IssueComment | PullRequest | Push | Create |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 21 | gharchive (full) | 78,940 | 169 | 50 | 510 | 591 | 1,156 | 63,633 | 8,104 |
| 22 | gharchive (full) | 72,584 | 179 | 54 | 569 | 764 | 1,256 | 58,308 | 7,275 |
| 23 | gharchive (full) | 71,174 | 213 | 55 | 506 | 705 | 1,235 | 57,719 | 6,735 |
| 21 | opendigger (first 7.3 MB) | 9,567 | 218 | 44 | 770 | 866 | 1,585 | 4,354 | 587 |
| 22 | opendigger (first 8.4 MB) | 11,836 | 288 | 68 | 741 | 1,023 | 1,915 | 5,691 | 713 |
| 23 | opendigger (first 9.4 MB) | 14,012 | 307 | 75 | 718 | 1,071 | 2,236 | 7,104 | 904 |

WatchEvent (full hours, gharchive): **169, 179, 213 per hour** = 0.21-0.30 % of events. For
comparison, 2024 baseline is about 8,000 per hour (3.4 % of events); `reports/capture_quality.md`
puts 2026-10-01..11 at 0.03-0.09 of the 2024 same-weekday median. The partial OpenDigger heads show
a WatchEvent share of 2.3 % (218-307 stars in 9.6-14 k events), which is far closer to the 2024 share
than gharchive's 0.2 %, but a file head is ordered differently from a whole hour (push share 45 %
vs 80 %), so this is a hint, not evidence.

## 4. Star capture vs ground truth: not measurable as specified

The second GO criterion (about 100 repos against the stargazers API with `starred_at`, close to the
2024 GH Archive capture level) cannot be evaluated:

1. **GitHub removed public stargazer lists in July 2026.** Verified 2026-10-12 with the new classic
   no-scope PAT (valid, `x-oauth-scopes` empty, 5,000 req/h): `GET /repos/{o}/{r}/stargazers` and
   `/repositories/{id}/stargazers` return 404 for every public repository tried (torvalds/linux,
   astral-sh/uv, octocat/Hello-World, others), and GraphQL `stargazers` returns `totalCount: 0` with no
   edges, while `stargazerCount` still returns the true total (90,627 for astral-sh/uv). GitHub's
   docs say: "Access to the stargazers listing endpoints will be limited to admins and
   collaborators" (changelog 2026-06-30). Only repositories we administer expose them.
2. Throughput makes it moot anyway: complete OpenDigger hours cannot be obtained within any
   reasonable time from either the runner or the laptop.

What remains available as ground truth is the **daily `stargazerCount`** (net of unstars, no
timestamps). A capture check would be: snapshot counts at the start and end of a window, compare
the delta with WatchEvents in the same window per source. That needs complete hours from the
source under test, which is exactly what OpenDigger fails to deliver.

## 5. Decision recorded

- OpenDigger: not enabled; rows never to be published (ADR-010).
- Live-source gate item 5: NO-GO branch applies; the API-first design note is **not yet written**,
  per instruction, pending your review of this report. One constraint discovered here changes its
  scope: the stargazers listing it assumed for part (b) is gone (ADR-010).
