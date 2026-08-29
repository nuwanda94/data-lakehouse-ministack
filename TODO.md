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
- [ ] test: Integration tests for full Bronze → Silver → Gold
- [ ] docs: Document zone contracts & data dictionary

## Later Phases
See the full plan in the original documentation / PDF.

## Progress Log
See `PROGRESS.md` (updated by the hourly-chore-feat automation).
