# Platform compact after retention

Post-v1.0 increment: a scheduled **expire-then-compact** job that covers
every medallion zone plus Silver and Gold quarantine. Zone commands stay
available (`bronze-maintain`, `silver-maintain`, `quarantine-maintain`,
`maintain`, `gold-quarantine-maintain`). `platform-maintain` is the
operator path that runs them in order.

Each zone expires old Hive prefixes first so compaction never rewrites
objects that the next step would delete. Silver quarantine runs after
Silver; Gold quarantine runs after Gold so the cleaned path is
maintained before the rejected-metric side path.

## What it measures

* Job: `platform.maintain`
* Order: Bronze → Silver → Quarantine → Gold → Gold quarantine
  (each: expire → compact)
* Live path: reuse `lakehouse.bronze_maintain`, `lakehouse.silver_maintain`,
  `lakehouse.quarantine_maintain`, `lakehouse.maintain`,
  `lakehouse.gold_quarantine_maintain`
* Spec path: the hermetic fixtures from those modules

When S3 is unreachable the command still evaluates against the hermetic
spec (`backend=spec`).

## Commands

```bash
python -m lakehouse platform-maintain
python -m lakehouse platform-maintain --apply
make platform-maintain
```

`--apply` is forwarded to every zone. Spec backend never writes. Exit
code `1` means any zone reported a failure.
