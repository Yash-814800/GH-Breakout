---
license: mit
pretty_name: gh-breakout derived tables
tags:
- github
- gharchive
- parquet
- feature-store
---

# gh-breakout derived tables

Enrichment, point-in-time features, labels and training tables derived from the
[events lake](https://huggingface.co/datasets/$events_repo) by the
[gh-breakout]($project_url) project (repository metadata, actor account ages, trending history,
Hacker News mentions, candidate features and labels).

Contents appear as the project's phases land: `enrich/`, `features/`, `labels/`, `training/`.
MIT license for the project's own processing and derived tables; no rights are claimed in
underlying GitHub data, repository names or logins. Key on `repo_id`, never on repository name.
