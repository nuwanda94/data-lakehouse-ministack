# Silver compact after retention

Post-v1.0 increment: a scheduled **expire-then-compact** job for Silver
cleaned events. Retention and compact stay available as standalone
commands. `silver-maintain` is the operator path that runs them in order.

Old Hive `events/event_type=/dt=` partitions are marked expire first so
compaction never rewrites objects that the next step would delete.

## What it measures

* Dataset: `silver.cleaned_events`
* Order: expire → compact
* Retention budget: `LAKEHOUSE_SILVER_RETENTION_DAYS` (default 60) or `--retention-days`
* Compact budget: `LAKEHOUSE_SILVER_COMPACT_MAX_OBJECTS` (default 8) or `--max-objects`
* Live path: reuse `lakehouse.silver_retention` and `lakehouse.silver_compact`
* Spec path: the hermetic fixtures from both modules

When S3 is unreachable the command still evaluates against the hermetic
spec (`backend=spec`).

## Commands

```bash
python -m lakehouse silver-maintain
python -m lakehouse silver-maintain --retention-days 30 --max-objects 4
python -m lakehouse silver-maintain --apply
make silver-maintain
SILVER_RETENTION_DAYS=30 SILVER_COMPACT_MAX_OBJECTS=4 make silver-maintain
```

`--apply` is forwarded to both steps. Spec backend never writes. Exit
code `1` means retention or compact reported a failure.
