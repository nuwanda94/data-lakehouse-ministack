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

## 2026-08-29 23:43 IST
- Completed: feat: Idempotency keys & exactly-once semantics
- Next candidate: feat: Late-arriving data handling (P1)
- Notes: Zone handlers now derive `run_id` from `idempotency_key(scope, sorted object keys)`. A succeeded DynamoDB run is replayed (`idempotent_replay=true`) instead of being rewritten. Failed runs stay retryable under the same id. See `docs/idempotency.md` and `lakehouse.pipeline.idempotency`.

## 2026-08-29 23:00 IST
- Completed: feat: Dead-letter handling & reprocessing
- Next candidate: feat: Idempotency keys & exactly-once semantics (P1)
- Notes: Bronze events queue now has a Terraform DLQ + redrive policy (`maxReceiveCount=3`). Local drain copies failed messages onto the DLQ. `python -m lakehouse dlq` / `redrive` and `make dlq` / `make redrive` move poison payloads back onto the source queue. See `docs/dlq.md`.

## 2026-08-29 22:00 IST
- Completed: feat: Step Functions state machine
- Next candidate: feat: Dead-letter handling & reprocessing (P1)
- Notes: Checked in ASL (`infra/terraform/sfn.asl.json.tftpl`) plus `aws_sfn_state_machine.medallion` that invokes ingest → silver → quality → Choice → gold with Retry/Catch. `lakehouse.orchestration.sfn` is the source-of-truth graph and a local interpreter (`python -m lakehouse sfn` / `make sfn`) so MiniStack does not need working SFN for the inner loop. Unit tests lock the Terraform template to the Python definition.

## 2026-08-29 21:00 IST
- Completed: ci: Pre-commit + required status checks
- Next candidate: feat: Step Functions state machine (P1) or feat: Structured metrics (CloudWatch + custom) (P1)
- Notes: Tightened `.pre-commit-config.yaml`. Added a `pre-commit` GitHub Actions job plus `make pre-commit`. Documented required status-check names in `docs/ci.md`.

## 2026-08-29 20:02 IST
- Completed: ci: Full CI pipeline with MiniStack
- Next candidate: ci: Pre-commit + required status checks (P0)

## 2026-08-29 19:05 IST
- Completed: docs: Document zone contracts & data dictionary

## 2026-08-29 18:06 IST
- Completed: test: Integration tests for full Bronze → Silver → Gold

## 2026-08-29 12:41 IST
- Completed: chore: Wire S3 event notifications or EventBridge

## 2026-08-29 10:35 IST
- Completed: chore: Lambda packaging & deployment via Terraform

## 2026-08-28 23:00 IST
- Completed: feat: Pipeline run metadata & status tracking

## 2026-08-28 21:00 IST
- Completed: feat: Quality gate as a first-class step

## 2026-08-28 20:00 IST
- Completed: feat: Gold aggregation Lambda

## 2026-08-28 19:05 IST
- Completed: feat: Silver transform Lambda

## 2026-08-28 18:08 IST
- Completed: feat: Bronze event-driven ingestion via S3 → SQS → Lambda

## 2026-08-28 12:48 IST
- Completed: test: Expand unit tests for seed + transform

## 2026-08-28 12:36 IST
- Completed: docs: Add ADR-003: Local orchestration vs Step Functions

## 2026-08-28 09:03 IST
- Completed: docs: Expand README with exact run instructions & screenshots

## 2026-08-27 23:01 IST
- Completed: chore: Add `scripts/get_outputs.sh` or Python helper

## 2026-08-27 22:01 IST
- Completed: chore: Add `.env` loading helper

## 2026-08-27 21:00 IST
- Completed: chore: Make `make up/infra/seed/pipeline` fully reliable

## 2026-08-27 20:10 IST
- Completed: chore: Finalize package layout & imports

## 2026-08-27 (initial)
- Completed: chore: initial project scaffold + TODO.md + PROGRESS.md
- Repo created: https://github.com/nuwanda94/data-lakehouse-ministack
