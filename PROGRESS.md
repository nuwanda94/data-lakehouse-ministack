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

## 2026-09-03 21:10 IST
- Completed: feat: Lineage edge weights from live object counts
- Next candidate: feat: Lineage path ratios (cleanse vs reject vs quarantine)
- Notes: Spec + live edges now stamp `weight` from the destination node's object count. Mermaid labels include the weight (`bronze -->|cleanse 18| silver`). CLI JSON exposes `edge_weights` and quarantine subgraph incoming/outgoing weight sums. Docs in `docs/lineage.md`.

## 2026-09-03 18:08 IST
- Completed: feat: Combined quarantine lineage subgraph (Silver + Gold side paths)
- Next candidate: feat: Lineage edge weights from live object counts
- Notes: Spec + live snapshots now expose `quarantine_subgraph` (nodes `silver_quarantine` + `gold_quarantine`, incoming reject/quarantine/unreadable edges, outgoing `run_metadata`). Mermaid wraps those leaves in `subgraph quarantine["quarantine side paths"]`. CLI JSON includes incoming/outgoing counts. Docs in `docs/lineage.md`.

## 2026-09-03 17:00 IST
- Completed: feat: Silver quarantine lineage edges (cleansed vs quality-quarantine side path)
- Next candidate: feat: Combined quarantine lineage subgraph (Silver + Gold side paths)
- Notes: Lineage spec + live graphs now include a `silver_quarantine` node (`quality_quarantine` under Silver `quarantine/`). Edges: `bronze -->|reject| silver_quarantine`, `quality -->|quarantine| silver_quarantine`, plus `run_metadata` to DynamoDB. Live object counts use the Silver `quarantine/` prefix. Docs in `docs/lineage.md`.

## 2026-09-03 16:00 IST
- Completed: feat: Gold quarantine lineage edges (metrics vs rejected-metric side path)
- Next candidate: feat: Silver quarantine lineage edges (cleansed vs quality-quarantine side path)
- Notes: Lineage spec + live graphs now include a `gold_quarantine` node (`rejected_metrics` under Gold `quarantine/`). Edges: `quality -->|reject| gold_quarantine`, `silver -->|unreadable| gold_quarantine`, plus `run_metadata` to DynamoDB. Live object counts use the Gold `quarantine/` prefix. Docs in `docs/lineage.md`.

## 2026-09-03 15:05 IST
- Completed: chore: include gold-quarantine in platform-maintain
- Next candidate: feat: Gold quarantine lineage edges (metrics vs rejected-metric side path)
- Notes: `platform-maintain` now chains Bronze → Silver → Quarantine → Gold → Gold quarantine. Spec fixtures expire 5 partitions and compact 5 fragmented prefixes. Describe JSON exposes `gold_quarantine_job`. Docs in `docs/platform-maintain.md`.

## 2026-09-03 14:15 IST
- Completed: chore: gold-quarantine compact-after-retention
- Next candidate: chore: include gold-quarantine in platform-maintain
- Notes: Gold quarantine now has a scheduled expire-then-compact job (`gold.quarantine.maintain`). Spec fixtures expire 1 stale partition then compact 1 fragmented prefix. CLI: `python -m lakehouse gold-quarantine-maintain` / `make gold-quarantine-maintain`. Docs in `docs/gold-quarantine-maintain.md`. CLI dispatch restored so existing command tests pass.

## 2026-09-03 14:05 IST
- Completed: feat: Gold quarantine compact / rewrite policy
- Next candidate: chore: gold-quarantine compact-after-retention
- Notes: Gold `quarantine/` Hive partitions with more than `LAKEHOUSE_GOLD_QUARANTINE_COMPACT_MAX_OBJECTS` (default 2) siblings are rewritten to `part-000.json`. Spec fixtures keep one compact `unreadable_silver` partition and compact a fragmented `unknown_event_type` prefix. CLI: `python -m lakehouse gold-quarantine-compact` / `make gold-quarantine-compact`. Docs in `docs/gold-quarantine-compact.md`.
