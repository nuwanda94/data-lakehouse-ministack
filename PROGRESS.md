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

## 2026-09-03 14:15 IST
- Completed: chore: gold-quarantine compact-after-retention
- Next candidate: chore: include gold-quarantine in platform-maintain
- Notes: Gold quarantine now has a scheduled expire-then-compact job (`gold.quarantine.maintain`). Spec fixtures expire 1 stale partition then compact 1 fragmented prefix. CLI: `python -m lakehouse gold-quarantine-maintain` / `make gold-quarantine-maintain`. Docs in `docs/gold-quarantine-maintain.md`. CLI dispatch restored so existing command tests pass.

## 2026-09-03 14:05 IST
- Completed: feat: Gold quarantine compact / rewrite policy
- Next candidate: chore: gold-quarantine compact-after-retention
- Notes: Gold `quarantine/` Hive partitions with more than `LAKEHOUSE_GOLD_QUARANTINE_COMPACT_MAX_OBJECTS` (default 2) siblings are rewritten to `part-000.json`. Spec fixtures keep one compact `unreadable_silver` partition and compact a fragmented `unknown_event_type` prefix. CLI: `python -m lakehouse gold-quarantine-compact` / `make gold-quarantine-compact`. Docs in `docs/gold-quarantine-compact.md`.
