# ADR-005: Parquet on S3 + Glue/Athena as the query surface

- **Status:** Accepted
- **Date:** 2026-08-30
- **Deciders:** project maintainers
- **Related:** `docs/catalog.md`, `docs/athena.md`, `docs/partitions.md`, `docs/cost-performance.md`

## Context

Gold has to be queryable by an analyst without downloading objects by hand.
Options:

1. **Parquet in S3** + Glue Data Catalog + Athena workgroup + named queries.
2. Load Gold into **Redshift / Snowflake / BigQuery**.
3. Query JSON in place with Athena or DuckDB and skip a catalog.

## Decision

**Silver and Gold are Parquet-shaped objects under Hive-style partitions.
Glue tables + an Athena workgroup are the AWS query surface. Catalog APIs
are feature-flagged so MiniStack applies stay cheap.**

- Partition projection (or explicit partition registration) is required so
  Athena does not list every key.
- Named queries target Gold grain only. Scanning Bronze in Athena is a
  documented anti-pattern (`docs/cost-performance.md`).
- DynamoDB `gold-metrics` is a serving copy of the same daily grain for the
  CLI, not a warehouse.

dbt on Athena is deferred (Phase 3 P2). It must sit *on* these tables, not
replace them.

## Consequences

- Cost is dominated by bytes scanned; the workgroup cutoff exists for a
  reason.
- MiniStack may not implement every Glue/Athena API; `make query` therefore
  also reads objects and DynamoDB directly.
- Schema comments and types in Glue must stay aligned with
  `configs/contracts/` (enforced by contract tests, not by Glue alone).

## Alternatives considered

| Option | Why not |
| --- | --- |
| Warehouse load every run | Extra service, extra bill, weaker "lakehouse" lesson. |
| Iceberg / Hudi / Delta now | Correct next step for concurrent writes; too much for demo volume and MiniStack coverage. Revisit if we add streaming. |
| DuckDB-only notebooks | Fine as a P2 UI; not the portable AWS contract. |
