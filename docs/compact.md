# Gold metric-object compact / rewrite policy

Post-v1.0 increment: a first-class **compaction policy** for Gold daily
metrics. Hive `metric=/dt=` partitions with more objects than the budget
are listed for rewrite. Compaction is opt-in (`--apply`); the default is
a dry-run plan.

Gold aggregation writes one `part-000.json` per (metric, day). Replays,
late-arriving windows, and overlapping runs can leave extra `part-*.json`
siblings in the same prefix. Compaction folds those payloads into a
single object so Athena / Glue scans stay cheap.

## What it measures

* Dataset: `gold.daily_metrics`
* Grain: Hive `metrics/metric={type}/dt={YYYY-MM-DD}/`
* Budget: `LAKEHOUSE_GOLD_COMPACT_MAX_OBJECTS` (default 2) or `--max-objects`
* Rule: keep when `objects <= max_objects`, compact otherwise
* Rewrite target: `metrics/metric={type}/dt={day}/part-000.json`
* Live path: discover keys under Gold `metrics/` when MiniStack answers
* Spec path: one already-compact partition + one fragmented partition

When S3 is unreachable the command still evaluates against the hermetic
spec (`backend=spec`).

## Commands

```bash
python -m lakehouse compact
python -m lakehouse compact --max-objects 4
python -m lakehouse compact --apply
make compact
GOLD_COMPACT_MAX_OBJECTS=4 make compact
```

`--apply` only rewrites partitions the plan marked `compact`. Spec
backend never writes. Exit code `1` means a live rewrite or delete
failed.
