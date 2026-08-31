# ADR-002: Medallion zones on object storage

- **Status:** Accepted
- **Date:** 2026-08-28
- **Deciders:** project maintainers
- **Related:** `configs/contracts/`, `docs/data-dictionary.md`, `docs/analytical-model.md`

## Context

We need a data model that teaches production lakehouse practice and still
fits a demo volume of JSON events. Alternatives:

1. **Medallion** — Bronze (raw), Silver (conformed), Gold (aggregates).
2. **Warehouse-first** — land events straight into a modelled warehouse table.
3. **Single bucket / single table** — one prefix, query everything raw.

## Decision

**Three S3 zones with explicit contracts, plus DynamoDB for run and metric
serving.**

| Zone | What lives there | Contract |
| --- | --- | --- |
| Bronze | Immutable producer JSON, partitioned by event date | `configs/contracts/bronze.json` |
| Silver | Conformed events (types, enums, quarantine flags) | `configs/contracts/silver.json` |
| Gold | Daily grain measures for analytics | `configs/contracts/gold.json` |

Zone logic is importable Python (`lakehouse.transforms`, `lakehouse.quality`)
so the Python runner and the Lambdas call the same functions.

DynamoDB holds `pipeline-runs` (control plane) and `gold-metrics` (low-latency
serving of the same Gold grain). It is not a second source of truth for
events; S3 remains the lake.

## Consequences

- Producers can be wrong without poisoning Gold: the quality gate quarantines.
- Analysts are steered at Gold (Athena named queries), not Bronze scans.
- Reprocessing a date is a zone rewrite, not a warehouse `DELETE`/`INSERT`
  dance we have not modelled.
- Extra moving parts (three buckets, three contracts) are accepted teaching
  cost.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Warehouse-first (Redshift / Snowflake / DuckDB only) | Hides object-store + catalog practice this repo exists to show. DuckDB/Athena can still query Gold. |
| Kappa / streaming-only | Optional Firehose path is Phase 5 P2; batch medallion is the v0.1 product. |
| One bucket, three prefixes only | Fine physically; we still want *named* buckets so IAM and event rules stay obvious. |

## Follow-ups

- dbt on Athena/Glue remains Phase 3 P2 and must read Gold, not rewrite it.
- Do not add a fourth "platinum" zone.
