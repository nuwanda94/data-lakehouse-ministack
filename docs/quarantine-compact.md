# Silver quarantine compact / rewrite

Post-v1.0 increment: a first-class **compact policy** for Silver
quarantine objects written by the quality gate. Prefixes under
`quarantine/reason=` with more objects than the budget are rewritten
into a single `part-000.json`.

Quality rejects land as one JSON object per event. Compaction folds
those siblings so the diagnostic zone stays cheap to list and expire.

## What it measures

* Dataset: `silver.quarantine`
* Grain: `quarantine/reason={reason}/`
* Budget: `LAKEHOUSE_QUARANTINE_COMPACT_MAX_OBJECTS` (default 8) or `--max-objects`
* Rule: compact when `objects > max_objects`, keep otherwise
* Live path: discover keys under Silver `quarantine/` when MiniStack answers
* Spec path: one kept `schema` prefix + one fragmented `poison` prefix

When S3 is unreachable the command still evaluates against the hermetic
spec (`backend=spec`).

## Commands

```bash
python -m lakehouse quarantine-compact
python -m lakehouse quarantine-compact --max-objects 4
python -m lakehouse quarantine-compact --apply
make quarantine-compact
QUARANTINE_COMPACT_MAX_OBJECTS=4 make quarantine-compact
```

`--apply` rewrites marked prefixes and deletes siblings. Spec backend
never writes. Exit code `1` means a live rewrite or delete failed.
