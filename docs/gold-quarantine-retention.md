# Gold quarantine retention / TTL

Post-v1.0 increment: a first-class **TTL policy** for Gold quarantine
objects written by the Gold handler. Partitions older than the budget are
listed for expiry. Deletes are opt-in (`--apply`); the default is a dry-run
plan.

Gold quarantine is a diagnostic zone. Keep it shorter-lived than
`metrics/` so rejected aggregates do not accumulate next to KPIs.

## What it measures

* Dataset: `gold.quarantine`
* Grain: Hive partition `quarantine/reason={reason}/metric={event_type}/dt={YYYY-MM-DD}/`
* Age: partition `dt` vs `as_of`
* Budget: `LAKEHOUSE_GOLD_QUARANTINE_RETENTION_DAYS` (default 30) or `--retention-days`
* Rule: keep when `dt >= as_of - retention_days`, expire otherwise
* Live path: discover keys under Gold `quarantine/` when MiniStack answers
* Spec path: two recent rejected metrics + one partition older than the budget

When S3 is unreachable the command still evaluates against the hermetic
spec (`backend=spec`).

## Commands

```bash
python -m lakehouse gold-quarantine-retention
python -m lakehouse gold-quarantine-retention --retention-days 14
python -m lakehouse gold-quarantine-retention --apply
make gold-quarantine-retention
GOLD_QUARANTINE_RETENTION_DAYS=14 make gold-quarantine-retention
```

`--apply` only deletes objects that the plan marked `expire`. Spec
backend never deletes. Exit code `1` means a live delete failed.

See also [`docs/gold-quarantine.md`](gold-quarantine.md) for the write path.
