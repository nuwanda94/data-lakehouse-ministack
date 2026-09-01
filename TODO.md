# Implementation TODO (from Implementation Plan)

Track progress of the medallion lakehouse. Highest priority incomplete items first.

## Phase 0 — Foundation Hardening (P0)

- [x] chore: Finalize package layout & imports
- [x] chore: Make `make up/infra/seed/pipeline` fully reliable
- [x] chore: Add `.env` loading helper
- [x] chore: Add `scripts/get_outputs.sh` or Python helper
- [x] docs: Expand README with exact run instructions & screenshots
- [x] docs: Add ADR-003: Local orchestration vs Step Functions
- [x] test: Expand unit tests for seed + transform

## Phase 1 — Core Medallion Pipeline (P0)

- [x] feat: Bronze event-driven ingestion via S3 → SQS → Lambda
- [x] feat: Silver transform Lambda
- [x] feat: Gold aggregation Lambda
- [x] feat: Quality gate as a first-class step
- [x] feat: Pipeline run metadata & status tracking
- [x] chore: Lambda packaging & deployment via Terraform
- [x] chore: Wire S3 event notifications or EventBridge
- [x] test: Integration tests for full Bronze → Silver → Gold
- [x] docs: Document zone contracts & data dictionary

## Phase 2 — Orchestration & Reliability (P1)

- [x] feat: Step Functions state machine
- [x] feat: Dead-letter handling & reprocessing
- [x] feat: Idempotency keys & exactly-once semantics
- [x] feat: Late-arriving data handling
- [x] chore: Centralized configuration (SSM or config file)
- [x] test: Failure injection tests
- [x] docs: Runbook: how to reprocess a date / debug a failed run

## Phase 3 — Catalog, Query & Analytics (P1/P2)

- [x] feat: Glue Data Catalog tables for Silver & Gold
- [x] feat: Athena workgroup + named queries
- [x] feat: dbt project on top of Athena/Glue
- [x] feat: Simple query UI or notebook
- [x] chore: Partition projection / partition management
- [x] docs: Analytical data model documentation

## Phase 4 — Observability & Platform (remaining P0/P1)

- [x] ci: Full CI pipeline with MiniStack (P0)
- [x] ci: Pre-commit + required status checks (P0)
- [x] feat: Structured metrics (CloudWatch + custom)
- [x] feat: Data quality dashboard / summary
- [x] feat: Schema evolution & contract testing
- [x] feat: Multi-environment support (local / real AWS)
- [x] chore: Cost & performance notes in README
- [x] docs: Architecture Decision Records for remaining big choices

## Phase 5 — Polish & Showcase

- [x] feat: One-command demo mode (`make demo`)
- [x] feat: Optional streaming path (Kinesis / Firehose)
- [x] docs: High-quality README with diagrams, GIFs, clear value proposition
- [x] docs: CONTRIBUTING.md + CODEOWNERS
- [x] chore: Release tagging + CHANGELOG
- [x] chore: Security scanning (Checkov, Trivy, detect-secrets)
- [x] refactor: Extract shared libraries cleanly
- [x] docs: “Skills demonstrated” + hiring-manager friendly section

## Post-v1.0 increments

- [x] feat: Dataset lineage snapshot (Bronze → Silver → quality → Gold)
- [x] feat: Gold freshness SLA (last-written vs max-age hours)
- [x] feat: Gold retention / partition expiry policy
- [x] feat: Silver quarantine retention / TTL
- [x] feat: Bronze raw object retention / TTL
- [x] feat: Silver cleaned-event retention / TTL

## Progress Log
See `PROGRESS.md` (updated by the hourly-chore-feat automation).
