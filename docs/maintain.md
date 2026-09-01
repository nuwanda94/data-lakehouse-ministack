# Gold compact after retention

Post-v1.0 increment: a scheduled **expire-then-compact** job for Gold
daily metrics. Retention and compact stay available as standalone
commands. `maintain` is the operator path that runs them in order.

Old Hive `metrics/metric=/dt=` partitions are marked expire first so
compaction never rewrites objects that the next step would delete.

## What it measures

* Dataset: `gold.daily_metrics`
* Order: expire → compact
* Retention budget: `LAKEHOUSE_GOLD_RETENTION_DAYS` (default 90) or `--retention-days`
* Compact budget: `LAKEHOUSE_GOLD_COMPACT_MAX_OBJECTS` (default 2) or `--max-objects`
* Live path: reuse `lakehouse.retention` and `lakehouse.compact`
* Spec path: the hermetic fixtures from both modules

When S3 is unreachable the command still evaluates against the hermetic
spec (`backend=spec`).

## Commands

```bash
python -m lakehouse maintain
python -m lakehouse maintain --retention-days 30 --max-objects 4
python -m lakehouse maintain --apply
make maintain
RETENTION_DAYS=30 GOLD_COMPACT_MAX_OBJECTS=4 make maintain
```

`--apply` is forwarded to both steps. Spec backend never writes. Exit
code `1` means retention or compact reported a failure.
