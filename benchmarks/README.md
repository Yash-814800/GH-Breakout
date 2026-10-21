# DuckDB vs clickhouse-local

Six equivalent queries (seven timed variants) on the same Parquet files: one year (2022) of `WatchEvent`,
`IssueCommentEvent` and `PullRequestEvent` from the lake (about 4.5 GB, 256 M rows). The write-up with the
results and caveats is `docs/blog/duckdb-vs-clickhouse.md` (published at `/blog/duckdb-vs-clickhouse/`).

```bash
# 1. data: copy the year from the lake (or `breakout lake pull --types ... --since 2022-01-01 --until 2022-12-31`)
mkdir -p ~/.cache/ghb-bench/data/{WatchEvent,IssueCommentEvent,PullRequestEvent}
for t in WatchEvent IssueCommentEvent PullRequestEvent; do
  cp data/lake/events/event_type=$t/year=2022/month=*/*.parquet ~/.cache/ghb-bench/data/$t/
done
# 2. clickhouse-local: the official single binary (LTS 26.8.32.14 was used), nothing to install
# 3. run under a memory cap; results go to benchmarks/results.json
systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 -p CPUQuota=400% \
  uv run python benchmarks/run.py --data ~/.cache/ghb-bench/data --clickhouse /path/to/clickhouse
# 4. table and chart
uv run python benchmarks/report.py
```

- `sql/duckdb/` and `sql/clickhouse/` hold the two dialects of each query; `{DATA}` is the data directory.
- The final result of every query is small (an aggregate row or a top-N list) and the harness compares the
  two engines' results exactly; Q6b is an estimate and is compared against the exact counts instead.
- Method: per query and engine, the data files are evicted from the page cache (`posix_fadvise`), then one
  cold and five warm runs, each in a fresh process. In-engine query time, wall time and the peak resident
  memory of the process are recorded. Both engines get 4 threads and a 4 GB memory limit; ClickHouse also gets
  external group-by/sort spilling at one third of that and `join_algorithm=auto`.
- `results_highmem.json` repeats the queries that did not finish at 4 GB with a larger limit.
