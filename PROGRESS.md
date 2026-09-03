# Progress Log — hourly-chore-feat automation

This file is updated by the `hourly-chore-feat` automation on every run.

## Format

```
## YYYY-MM-DD HH:MM TZ
- Completed: <type>: <title>
- Next candidate: <type>: <title> (P0/P1)
- Notes: ...
```

## Runs

## 2026-09-03 13:10 IST
- Completed: feat: Gold quarantine / rejected-metric side path
- Next candidate: feat: Gold quarantine retention / TTL
- Notes: Gold handler now partitions contract-invalid aggregates and unreadable Silver payloads onto `gold/quarantine/reason=/metric=/dt=/part-000.json`. Valid metrics still land in `metrics/` + DynamoDB. Hermetic tests cover unreadable Silver and `partition_gold_metrics`. Docs in `docs/gold-quarantine.md`.

## 2026-09-03 12:00 IST
- Completed: chore: include quarantine in platform-maintain
- Next candidate: feat: Gold quarantine / rejected-metric side path
- Notes: `platform-maintain` now chains Bronze → Silver → Quarantine → Gold expire-then-compact. Spec fixtures sum to expire_count=4 and compact_count=4. Quarantine runs after Silver so cleaned events are maintained before the failed-row prefix. Docs in `docs/platform-maintain.md`.
