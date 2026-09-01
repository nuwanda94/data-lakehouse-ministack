# Quarantine compact after retention

Post-v1.0 increment: a scheduled **expire-then-compact** job for Silver
quarantine. Retention and compact stay available as standalone
commands. `quarantine-maintain` is the operator path that runs them in
order.

Objects older than the TTL window are marked expire first so compaction
never rewrites payloads the next step would delete.

## What it measures

* Dataset: `silver.quarantine`
* Order: expire → compact
* Retention budget: `LAKEHOUSE_QUARANTINE_RETENTION_DAYS` (default 14) or `--retention-days`
* Compact budget: `LAKEHOUSE_QUARANTINE_COMPACT_MAX_OBJECTS` (default 8) or `--max-objects`
* Live path: reuse `lakehouse.quarantine_retention` and `lakehouse.quarantine_compact`
* Spec path: the hermetic fixtures from both modules

When S3 is unreachable the command still evaluates against the hermetic
spec (`backend=spec`).

## Commands

```bash
python -m lakehouse quarantine-maintain
python -m lakehouse quarantine-maintain --retention-days 7 --max-objects 4
python -m lakehouse quarantine-maintain --apply
make quarantine-maintain
QUARANTINE_RETENTION_DAYS=7 QUARANTINE_COMPACT_MAX_OBJECTS=4 make quarantine-maintain
```

`--apply` is forwarded to both steps. Spec backend never writes. Exit
code `1` means retention or compact reported a failure.
