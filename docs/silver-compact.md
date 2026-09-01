# Silver cleaned-event compact / rewrite policy

Post-v1.0 increment: a first-class **compaction policy** for Silver
cleaned events. Hive `event_type=/dt=` partitions with more objects than
the budget are listed for rewrite. Compaction is opt-in (`--apply`); the
default is a dry-run plan.

Silver writes one `{event_id}.json` per cleaned event. Overlapping runs
and late arrivals can leave many tiny files in the same type + day
prefix. Compaction folds those payloads into a single `part-000.json`
so Gold scans and Athena listings stay cheap.

## What it measures

* Dataset: `silver.cleaned_events`
* Grain: Hive `events/event_type={type}/dt={YYYY-MM-DD}/`
* Budget: `LAKEHOUSE_SILVER_COMPACT_MAX_OBJECTS` (default 8) or `--max-objects`
* Rule: keep when `objects <= max_objects`, compact otherwise
* Rewrite target: `events/event_type={type}/dt={day}/part-000.json`
* Live path: discover keys under Silver `events/` when MiniStack answers
* Spec path: one already-compact partition + one fragmented partition

When S3 is unreachable the command still evaluates against the hermetic
spec (`backend=spec`).

## Commands

```bash
python -m lakehouse silver-compact
python -m lakehouse silver-compact --max-objects 4
python -m lakehouse silver-compact --apply
make silver-compact
SILVER_COMPACT_MAX_OBJECTS=4 make silver-compact
```

`--apply` only rewrites partitions the plan marked `compact`. Spec
backend never writes. Exit code `1` means a live rewrite or delete
failed.
