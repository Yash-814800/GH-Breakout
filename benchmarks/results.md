| Query | DuckDB median / min (s) | ClickHouse median / min (s) | ClickHouse vs DuckDB (median) | Peak memory DuckDB / ClickHouse (MB) | Same result |
|---|---|---|---|---|---|
| Q1 daily stars | 2.08 / 1.99 | 4.78 / 4.53 | 2.3x slower | 1132 / 3160 | yes |
| Q2 7-day velocity, top 100 | 4.53 / 4.50 | 8.30 / 8.03 | 1.8x slower | 1338 / 3296 | yes |
| Q3 sessionization | 17.90 / 16.21 | did not finish / did not finish | - | 4393 / 4432 | n/a |
| Q4 cohort retention | 35.12 / 34.43 | did not finish / did not finish | - | 4798 / 4240 | n/a |
| Q5 co-star overlap | 0.95 / 0.94 | 2.81 / 2.75 | 3.0x slower | 593 / 2451 | yes |
| Q6a exact distinct | 2.08 / 1.95 | 1.71 / 1.65 | 1.2x faster | 1133 / 1149 | yes |
| Q6b approx distinct | 1.18 / 1.17 | 0.81 / 0.79 | 1.5x faster | 92 / 464 | estimate |

Cold run (first run after dropping the data files from the page cache), seconds:

| Query | DuckDB cold | ClickHouse cold |
|---|---|---|
| Q1 daily stars | 3.14 | 5.53 |
| Q2 7-day velocity, top 100 | 5.91 | 9.30 |
| Q3 sessionization | 21.43 | did not finish |
| Q4 cohort retention | 38.09 | did not finish |
| Q5 co-star overlap | 1.78 | 6.00 |
| Q6a exact distinct | 2.53 | 2.72 |
| Q6b approx distinct | 2.09 | 2.62 |

Queries that did not finish at 4 GB, repeated with a 6.0 GB engine memory limit (same data, threads and method), seconds:

| Query | DuckDB median / min | ClickHouse median / min | ClickHouse vs DuckDB | Peak memory DuckDB / ClickHouse (MB) | Same result |
|---|---|---|---|---|---|
| Q3 sessionization | 14.66 / 13.82 | 24.97 / 23.48 | 1.7x slower | 5302 / 5188 | yes |
| Q4 cohort retention | 33.83 / 29.97 | 50.98 / 50.65 | 1.5x slower | 6508 / 5268 | yes |

Approximate distinct count, error against the exact count (12 months): DuckDB mean 14.06%, max 32.80%; ClickHouse mean 0.60%, max 1.25%.
