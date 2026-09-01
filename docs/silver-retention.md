# Silver cleaned-event retention / TTL

Post-v1.0 increment: a first-class **retention policy** for Silver cleaned
events. Hive `dt=` partitions older than the budget are listed for expiry.
Deletes are opt-in (`--apply`); the default is a dry-run plan.

Silver is the conformed grain Gold aggregates from. Keep a longer window
than Bronze raw JSON (default 60 days vs 30) so late reprocessing and
quality investigations still have source rows.

## What it measures

* Dataset: `silver.cleaned_events`
* Grain: Hive `events/event_type={type}/dt={YYYY-MM-DD}/`
* Budget: `LAKEHOUSE_SILVER_RETENTION_DAYS` (default 60) or `--retention-days`
* Rule: keep when `dt >= as_of - retention_days`, expire otherwise
* Live path: discover keys under Silver `events/` when MiniStack answers
* Spec path: two recent event days + one day older than the budget

When S3 is unreachable the command still evaluates against the hermetic
spec (`backend=spec`).

## Commands

```bash
python -m lakehouse silver-retention
python -m lakehouse silver-retention --retention-days 21
python -m lakehouse silver-retention --apply
make silver-retention
SILVER_RETENTION_DAYS=21 make silver-retention
```

`--apply` only deletes objects whose Hive `dt=` the plan marked `expire`.
Spec backend never deletes. Exit code `1` means a live delete failed.
