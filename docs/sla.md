# Gold freshness SLA

Post-v1.0 increment: a first-class **freshness check** for Gold daily
metrics that does not require CloudWatch Alarms or a live MiniStack
session.

## What it measures

* Dataset: `gold.daily_metrics`
* Signal: last-written time of Gold `metrics/` objects, falling back to
  the latest succeeded pipeline run
* Budget: `LAKEHOUSE_GOLD_SLA_HOURS` (default 24) or `--max-age-hours`
* Result: `ok` when age ≤ budget, `breached` otherwise

When S3 or DynamoDB is unreachable the check still evaluates against the
hermetic spec (`backend=spec`, Gold written one hour ago).

## Commands

```bash
python -m lakehouse sla
python -m lakehouse sla --max-age-hours 6
make sla
```

The JSON printed by the CLI is what CI asserts on. Exit code `1` means
the live (or spec) snapshot is stale.
