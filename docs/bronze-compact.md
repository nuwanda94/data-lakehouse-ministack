# Bronze raw-object compact / rewrite policy

Post-v1.0 increment: a first-class **compaction policy** for Bronze raw
events. Hive `dt=` partitions with more objects than the budget are
listed for rewrite. Compaction is opt-in (`--apply`); the default is a
dry-run plan.

Bronze ingest writes one `{event_id}.json` per landing object. Seed
batches and overlapping producers can leave dozens of tiny files in the
same day prefix. Compaction folds those payloads into a single
`part-000.json` so later Silver scans stay cheap.

## What it measures

* Dataset: `bronze.raw_events`
* Grain: Hive `events/dt={YYYY-MM-DD}/`
* Budget: `LAKEHOUSE_BRONZE_COMPACT_MAX_OBJECTS` (default 8) or `--max-objects`
* Rule: keep when `objects <= max_objects`, compact otherwise
* Rewrite target: `events/dt={day}/part-000.json`
* Live path: discover keys under Bronze `events/` when MiniStack answers
* Spec path: one already-compact partition + one fragmented partition

When S3 is unreachable the command still evaluates against the hermetic
spec (`backend=spec`).

## Commands

```bash
python -m lakehouse bronze-compact
python -m lakehouse bronze-compact --max-objects 4
python -m lakehouse bronze-compact --apply
make bronze-compact
BRONZE_COMPACT_MAX_OBJECTS=4 make bronze-compact
```

`--apply` only rewrites partitions the plan marked `compact`. Spec
backend never writes. Exit code `1` means a live rewrite or delete
failed.
