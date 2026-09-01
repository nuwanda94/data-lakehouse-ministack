# Gold retention / partition expiry

Post-v1.0 increment: a first-class **retention policy** for Gold daily
metrics. Hive partitions older than the budget are listed for expiry.
Deletes are opt-in (`--apply`); the default is a dry-run plan.

## What it measures

* Dataset: `gold.daily_metrics`
* Grain: Hive `metrics/metric={type}/dt={YYYY-MM-DD}/`
* Budget: `LAKEHOUSE_GOLD_RETENTION_DAYS` (default 90) or `--retention-days`
* Rule: keep when `dt >= as_of - retention_days`, expire otherwise
* Live path: discover keys under Gold `metrics/` when MiniStack answers
* Spec path: two recent purchase partitions + one page_view older than the budget

When S3 is unreachable the command still evaluates against the hermetic
spec (`backend=spec`).

## Commands

```bash
python -m lakehouse retention
python -m lakehouse retention --retention-days 30
python -m lakehouse retention --apply
make retention
RETENTION_DAYS=30 make retention
```

`--apply` only deletes objects that the plan marked `expire`. Spec
backend never deletes. Exit code `1` means a live delete failed.
