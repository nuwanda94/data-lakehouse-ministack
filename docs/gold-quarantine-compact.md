# Gold quarantine compact / rewrite policy

Post-v1.0 increment: a first-class **compaction policy** for Gold
quarantine partitions. Hive `reason=/metric=/dt=` prefixes with more
objects than the budget are listed for rewrite. Compaction is opt-in
(`--apply`); the default is a dry-run plan.

Gold writes one `part-000.json` per rejected (reason, metric, day).
Replays and overlapping Gold runs can leave extra `part-*.json`
siblings in the same prefix. Compaction folds those payloads into a
single object so quarantine scans stay cheap and retention has one
object per partition to expire.

## What it measures

* Dataset: `gold.quarantine`
* Grain: Hive `quarantine/reason={reason}/metric={type}/dt={YYYY-MM-DD}/`
* Budget: `LAKEHOUSE_GOLD_QUARANTINE_COMPACT_MAX_OBJECTS` (default 2) or `--max-objects`
* Rule: keep when `objects <= max_objects`, compact otherwise
* Rewrite target: `quarantine/reason={reason}/metric={type}/dt={day}/part-000.json`
* Live path: discover keys under Gold `quarantine/` when MiniStack answers
* Spec path: one already-compact partition + one fragmented partition

When S3 is unreachable the command still evaluates against the hermetic
spec (`backend=spec`).

## Commands

```bash
python -m lakehouse gold-quarantine-compact
python -m lakehouse gold-quarantine-compact --max-objects 4
python -m lakehouse gold-quarantine-compact --apply
make gold-quarantine-compact
GOLD_QUARANTINE_COMPACT_MAX_OBJECTS=4 make gold-quarantine-compact
```

`--apply` only rewrites partitions the plan marked `compact`. Spec
backend never writes. Exit code `1` means a live rewrite or delete
failed.

See also [`docs/gold-quarantine.md`](gold-quarantine.md) for the write
path and [`docs/gold-quarantine-retention.md`](gold-quarantine-retention.md)
for TTL expiry.
