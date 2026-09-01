# Bronze compact after retention

Post-v1.0 increment: a scheduled **expire-then-compact** job for Bronze
raw events. Retention and compact stay available as standalone
commands. `bronze-maintain` is the operator path that runs them in order.

Old Hive `events/dt=` partitions are marked expire first so compaction
never rewrites objects that the next step would delete.

## What it measures

* Dataset: `bronze.raw_events`
* Order: expire → compact
* Retention budget: `LAKEHOUSE_BRONZE_RETENTION_DAYS` (default 30) or `--retention-days`
* Compact budget: `LAKEHOUSE_BRONZE_COMPACT_MAX_OBJECTS` (default 8) or `--max-objects`
* Live path: reuse `lakehouse.bronze_retention` and `lakehouse.bronze_compact`
* Spec path: the hermetic fixtures from both modules

When S3 is unreachable the command still evaluates against the hermetic
spec (`backend=spec`).

## Commands

```bash
python -m lakehouse bronze-maintain
python -m lakehouse bronze-maintain --retention-days 14 --max-objects 4
python -m lakehouse bronze-maintain --apply
make bronze-maintain
BRONZE_RETENTION_DAYS=14 BRONZE_COMPACT_MAX_OBJECTS=4 make bronze-maintain
```

`--apply` is forwarded to both steps. Spec backend never writes. Exit
code `1` means retention or compact reported a failure.
