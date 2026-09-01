# Bronze raw object retention / TTL

Post-v1.0 increment: a first-class **retention policy** for Bronze raw
landing objects. Hive `dt=` partitions older than the budget are listed
for expiry. Deletes are opt-in (`--apply`); the default is a dry-run plan.

Bronze is the cheapest zone to keep, but raw JSON still grows without a
cap. Expire old event days after Silver and Gold have already absorbed
them.

## What it measures

* Dataset: `bronze.raw_events`
* Grain: Hive `events/dt={YYYY-MM-DD}/`
* Budget: `LAKEHOUSE_BRONZE_RETENTION_DAYS` (default 30) or `--retention-days`
* Rule: keep when `dt >= as_of - retention_days`, expire otherwise
* Live path: discover keys under Bronze `events/` when MiniStack answers
* Spec path: two recent event days + one day older than the budget

When S3 is unreachable the command still evaluates against the hermetic
spec (`backend=spec`).

## Commands

```bash
python -m lakehouse bronze-retention
python -m lakehouse bronze-retention --retention-days 14
python -m lakehouse bronze-retention --apply
make bronze-retention
BRONZE_RETENTION_DAYS=14 make bronze-retention
```

`--apply` only deletes objects that the plan marked `expire`. Spec
backend never deletes. Exit code `1` means a live delete failed.
