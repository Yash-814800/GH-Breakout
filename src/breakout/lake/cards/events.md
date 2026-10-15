---
license: mit
pretty_name: gh-breakout events (slim GH Archive lake)
language:
- en
tags:
- github
- gharchive
- parquet
- events
- time-series
size_categories:
- $size_category
configs:
$configs
---

# gh-breakout events: a slim GitHub public-events lake

Public GitHub events (stars, forks, issues, pull requests, releases, repository creation) in a
compact, column-pruned Parquet layout, built for the
[gh-breakout]($project_url) project, which predicts which young repositories are about to
"break out" (gain an unusual number of stars in the next 30 days) and publishes a daily
leaderboard with an honest public track record.

## Provenance and license

- **Source:** [GH Archive](https://www.gharchive.org/), which records the public GitHub Events
  API stream. History before 2023-06 was extracted from the public BigQuery dataset
  `githubarchive` (spine columns only); 2023-06 onward is parsed from the hourly files at
  `data.gharchive.org`. Each row records its `source` and `detail_level`.
- **License:** MIT, which covers this project's own processing code and the derived tables
  published here. The project claims **no rights in the underlying GitHub events** or in the
  repository names and user logins they contain; those remain subject to GitHub's terms and to
  their authors' rights. Do not use this dataset to contact individuals.
- Rows from the OpenDigger mirror are never published here.

## Layout

```
events/event_type=<Type>/year=YYYY/month=MM/bq-YYYYMM.parquet      BigQuery history (before 2023-06)
events/event_type=<Type>/year=YYYY/month=MM/month-YYYYMM[-partNNN].parquet   compacted month
events/event_type=<Type>/year=YYYY/month=MM/day-YYYY-MM-DD.parquet  current, not yet compacted month
push_daily/year=YYYY/month=MM/{bq,month,day}-....parquet            PushEvent aggregated per day
manifests/                                                         ingest manifests
catalog.parquet                                                    one row per data file (see below)
```

`catalog.parquet` lists every file with its row count, size, SHA-256, min/max timestamp,
`detail_level` range, source range and schema version, so a client can choose files without
listing the repository.

Event types: $event_types. Files are sorted by `repo_id, created_at, event_id`.

## Schema (`events`, schema version $schema_version)

$events_schema

`push_daily` (PushEvent aggregated, one row per repo, actor and day):

$push_schema

## Coverage

$coverage

## Known caveats

- **Payload trimming (2025-10-07):** GitHub removed push commit lists, many pull-request fields and
  `author_association` from the Events API. For events after that date `pr_merged`,
  `target_user_id`, `target_created_at` and similar columns are NULL by construction.
- **Star capture degraded after 2025-05-23:** measured WatchEvent volume against 2024 baselines
  falls from ~0.7 on 2025-05-24 to ~0.01-0.1 in mid-2026 while other event types stay near
  normal. Treat star counts after 2025-05-23 as unreliable; the project's `trusted_end` is
  2025-05-23. See the project's `reports/capture_quality.md`.
- **Spine-only history:** events before 2023-06-01 have `detail_level = 0`; payload-derived
  columns (`action`, `number`, `is_pull_request`, `pr_merged`, ...) are NULL there.
- **Unstars are not recorded**: the stream only contains star events.
- **Bots are included**; no bot filtering is applied here.
- A few days are absent from every source (2020-08-22, 2021-08-26, 2021-10-26..28).
- Two hours are absent upstream (404 at data.gharchive.org): 2025-06-12 17:00 and 18:00 UTC.
- `repo_name` and `actor_login` are the names at event time; repositories are renamed and
  transferred, so always key on `repo_id` and `actor_id`.

## Update cadence

A daily GitHub Actions job appends the previous day as `day-*` files; once a month is complete
it is compacted into `month-*` files in one atomic commit (day files removed, catalog updated).

## Query with DuckDB

```sql
INSTALL httpfs; LOAD httpfs;
SELECT date_trunc('day', created_at) AS d, count(*) AS stars
FROM read_parquet('hf://datasets/$repo/events/event_type=WatchEvent/year=2024/month=06/*.parquet')
GROUP BY 1 ORDER BY 1 DESC LIMIT 5;
```

Use the catalog to find the files for a date range:

```sql
SELECT path FROM read_parquet('hf://datasets/$repo/catalog.parquet')
WHERE event_type = 'WatchEvent' AND year = 2024;
```
