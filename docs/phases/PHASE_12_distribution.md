# Phase 12 — Distribution: RSS, badges, weekly digest, Bluesky bot

## Goal
Get the predictions in front of people automatically, using only free channels.

## Prerequisites
Phase 10 (site) done; Phase 11 recommended (suspicion badges appear in feeds).

## Deliverables

### 12.1 Feeds (built with the site)
- `/feed.xml` (RSS 2.0, via `@astrojs/rss`) and `/feed.json` (JSON Feed 1.1): one item per **new leaderboard entry**
  (a repo entering the top `leaderboard_size` for the first time in 30 days), newest first, last 100 items. Item:
  title `owner/name — 34% breakout probability`, link to the repo page on the site, description = explanation
  sentence + age + stars 7d + suspicion note if any. GUID = `repo_id:first_flag_date` (stable).
- `/digest/feed.xml`: one item per weekly digest (12.3).
- Add `<link rel="alternate">` tags in the site head. Validate the feed XML in a test (parse with `feedparser`
  or `xml.etree` and check required fields).

### 12.2 Badges (shields.io endpoint badges, static JSON)
- `breakout publish badges` writes `site/public/badges/<repo_id>.json` and `site/public/badges/by-name/<owner>/<name>.json`
  for every repo flagged in the last 90 days, using the shields.io endpoint schema:
  `{"schemaVersion": 1, "label": "breakout radar", "message": "#7 today · 34%", "color": "<hex>"}`;
  for repos no longer on the board: `"message": "flagged 2026-09-14"` in a neutral color. Never encode
  suspicion in the badge.
- Repo pages show a copyable Markdown snippet:
  `![breakout radar](https://img.shields.io/endpoint?url=<urlencoded badge json url>)` linking back to the repo page.
- Document that `by-name` paths follow the current name and may break after a rename; `repo_id` paths are stable.

### 12.3 Weekly digest
- `breakout publish digest --week YYYY-Www` (run in `weekly.yml` after retrain) generates
  `site/src/content/digest/YYYY-Www.md` **data** (frontmatter + templated sections) — or JSON consumed by an Astro
  page at `/digest/YYYY-Www/`. Sections (templated text from data, no LLM):
  1. New on the board this week (top 10 by max probability), with explanation sentences
  2. Biggest movers
  3. Predictions that matured this week: hits and misses from 30 days ago (honest, including misses)
  4. Model & pipeline notes: model version changes, drift flags, missing data
- Digests are generated from frozen snapshots + outcomes only, so they are reproducible. Because the site build
  happens in `daily.yml`, store digest data in the derived HF repo (`digests/`) and have `publish site-data` pull it.
- `/digest/` index page listing all digests.

### 12.4 Bluesky bot (optional, `optional.bluesky_enabled`)
- Use the official `atproto` Python SDK with `BLUESKY_HANDLE` + `BLUESKY_APP_PASSWORD` (an app password, never the
  main password).
- Daily, after deploy succeeds: post up to 3 repos that newly entered the top 10 and have not been posted in the last
  60 days and are not high-suspicion. Format (≤ 300 characters, count graphemes): repo name, probability, one
  explanation clause, link to the site repo page. Use the SDK's rich-text builder so links are real link facets.
- Idempotency: record posted `(repo_id, date, post_uri)` in `derived/distribution/bluesky_posted.parquet`; never post the
  same repo twice within 60 days; `--dry-run` prints posts without sending (default in local runs).
- Weekly: post a link to the new digest.
- Failure must not fail the daily pipeline (log + status warning only).
- Document a Mastodon variant in the runbook (instance must explicitly allow bots; not implemented by default).

### 12.5 Optional: GitHub-native subscription
- Post each weekly digest to a GitHub Discussions category "Digest" via the GraphQL `createDiscussion` mutation
  (needs Discussions enabled and the category id) so followers can subscribe with GitHub notifications. Implement
  only if the human enables Discussions (HUMAN DECISION).

## Acceptance criteria
- [ ] `feed.xml` / `feed.json` validate and appear on the deployed site; subscribing in a reader works.
- [ ] A badge renders through shields.io for a flagged repo (paste the URL in the report).
- [ ] One digest page generated from real data; digest feed works.
- [ ] Bluesky dry run prints correct posts; if enabled, one real post succeeds and a second run does not repost.
