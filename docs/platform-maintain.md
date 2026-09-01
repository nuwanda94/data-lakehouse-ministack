# Platform compact after retention

Post-v1.0 increment: a scheduled **expire-then-compact** job that covers
every medallion zone. Zone commands stay available (`bronze-maintain`,
`silver-maintain`, `maintain`). `platform-maintain` is the operator path
that runs them in order.

Each zone expires old Hive partitions first so compaction never rewrites
objects that the next step would delete.

## What it measures

* Job: `platform.maintain`
* Order: Bronze → Silver → Gold (each zone: expire → compact)
* Live path: reuse `lakehouse.bronze_maintain`, `lakehouse.silver_maintain`,
  `lakehouse.maintain`
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
