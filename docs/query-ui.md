# Simple query UI and notebook

Phase 3 P2 adds an analyst surface that does **not** require Streamlit
or a live Athena API (MiniStack usually has neither).

## What you get

| Piece | Path / command |
| --- | --- |
| Snapshot helper | `lakehouse.query_ui.collect_snapshot()` |
| Self-contained HTML | `python -m lakehouse ui --out build/query-ui.html` |
| Notebook | [`notebooks/gold_query.ipynb`](../notebooks/gold_query.ipynb) |
| Named Athena SQL | same catalog as [`docs/athena.md`](athena.md) |

The HTML page shows:

1. Gold metrics from DynamoDB (`make query` source)
2. Gold object keys on S3
3. Recent pipeline runs
4. The four named Athena queries (SQL always visible; execution is optional)

When MiniStack or tables are missing, the command still exits 0 with
`backend=spec` so unit CI stays offline.

## Commands

```bash
# JSON summary (named queries + row counts)
python -m lakehouse ui

# Write the dashboard next to the repo
python -m lakehouse ui --out build/query-ui.html
make ui

# Optional local server (blocking; not used in CI)
python -m lakehouse ui --out build/query-ui.html --serve --port 8765
```

Open `build/query-ui.html` in a browser, or start Jupyter and run
`notebooks/gold_query.ipynb`.

On real AWS with `enable_athena=true`, start a named query from the same
SQL via `python -m lakehouse athena --name gold_daily_totals`.
