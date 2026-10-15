---
license: mit
pretty_name: gh-breakout frozen daily predictions
tags:
- github
- predictions
- parquet
---

# gh-breakout frozen daily predictions

One immutable `predictions/date=YYYY-MM-DD/predictions.parquet` per day, written by the daily
job of the [gh-breakout]($project_url) project **before** the outcome is known. This repository
is append-only: history is never squashed or rewritten, and the git ledger
(`ledger/predictions.csv`) in the code repository carries hashes of each day's file so the track
record is tamper-evident.
