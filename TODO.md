# Implementation TODO (from Implementation Plan)

Track progress of the medallion lakehouse. Highest priority incomplete items first.

## Phase 0 — Foundation Hardening (P0)

- [x] chore: Finalize package layout & imports
- [x] chore: Make `make up/infra/seed/pipeline` fully reliable
- [ ] chore: Add `.env` loading helper
- [ ] chore: Add `scripts/get_outputs.sh` or Python helper
- [ ] docs: Expand README with exact run instructions & screenshots
- [ ] docs: Add ADR-003: Local orchestration vs Step Functions
- [ ] test: Expand unit tests for seed + transform

## Phase 1 — Core Medallion Pipeline (P0)

- [ ] feat: Bronze event-driven ingestion via S3 → SQS → Lambda
- [ ] feat: Silver transform Lambda
- [ ] feat: Gold aggregation Lambda
- [ ] feat: Quality gate as a first-class step
- [ ] feat: Pipeline run metadata & status tracking
- [ ] chore: Lambda packaging & deployment via Terraform
- [ ] chore: Wire S3 event notifications or EventBridge
- [ ] test: Integration tests for full Bronze → Silver → Gold
- [ ] docs: Document zone contracts & data dictionary

## Later Phases
See the full plan in the original documentation / PDF.

## Progress Log
See `PROGRESS.md` (updated by the hourly-chore-feat automation).
