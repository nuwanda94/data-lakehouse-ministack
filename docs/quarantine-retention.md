# Silver quarantine retention / TTL

Post-v1.0 increment: a first-class **TTL policy** for Silver quarantine
objects written by the quality gate. Rows older than the budget are listed
for expiry. Deletes are opt-in (`--apply`); the default is a dry-run plan.

Quarantine is a diagnostic zone. Keep it short-lived so poison payloads do
not accumulate in Silver.

## What it measures

* Dataset: `silver.quarantine`
* Grain: object under `quarantine/reason={reason}/{event_id}.json`
* Age: S3 `LastModified` (spec fixtures use synthetic `written_at`)
* Budget: `LAKEHOUSE_QUARANTINE_RETENTION_DAYS` (default 14) or `--retention-days`
* Rule: keep when `written_at >= as_of - retention_days`, expire otherwise
* Live path: discover keys under Silver `quarantine/` when MiniStack answers
* Spec path: two recent objects + one poison object older than the budget

When S3 is unreachable the command still evaluates against the hermetic
spec (`backend=spec`).

## Commands

```bash
python -m lakehouse quarantine-retention
python -m lakehouse quarantine-retention --retention-days 7
python -m lakehouse quarantine-retention --apply
make quarantine-retention
QUARANTINE_RETENTION_DAYS=7 make quarantine-retention
```

`--apply` only deletes objects that the plan marked `expire`. Spec
backend never deletes. Exit code `1` means a live delete failed.
