# Gold quarantine compact after retention

Post-v1.0 increment: a scheduled **expire-then-compact** job for Gold
quarantine. Retention and compact stay available as standalone
commands. `gold-quarantine-maintain` is the operator path that runs
them in order.

Objects older than the TTL window are marked expire first so compaction
never rewrites payloads the next step would delete.

## What it measures

* Dataset: `gold.quarantine`
* Order: expire → compact
* Retention budget: `LAKEHOUSE_GOLD_QUARANTINE_RETENTION_DAYS` (default 30) or `--retention-days`
* Compact budget: `LAKEHOUSE_GOLD_QUARANTINE_COMPACT_MAX_OBJECTS` (default 2) or `--max-objects`
* Live path: reuse `lakehouse.gold_quarantine_retention` and `lakehouse.gold_quarantine_compact`
* Spec path: the hermetic fixtures from both modules

When S3 is unreachable the command still evaluates against the hermetic
spec (`backend=spec`).

## Commands

```bash
python -m lakehouse gold-quarantine-maintain
python -m lakehouse gold-quarantine-maintain --retention-days 14 --max-objects 4
python -m lakehouse gold-quarantine-maintain --apply
make gold-quarantine-maintain
GOLD_QUARANTINE_RETENTION_DAYS=14 GOLD_QUARANTINE_COMPACT_MAX_OBJECTS=4 make gold-quarantine-maintain
```

`--apply` is forwarded to both steps. Spec backend never writes. Exit
code `1` means retention or compact reported a failure.

See also [`docs/gold-quarantine-retention.md`](gold-quarantine-retention.md)
and [`docs/gold-quarantine-compact.md`](gold-quarantine-compact.md).
