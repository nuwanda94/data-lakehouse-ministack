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

## 2026-08-29 10:35 IST
- Completed: chore: Lambda packaging & deployment via Terraform
- Next candidate: chore: Wire S3 event notifications or EventBridge (P0)
- Notes: Added `lakehouse.ops.lambda_package` + `scripts/package_lambda.py` to zip `src/lakehouse` (optional pydantic vendor). Terraform now creates a shared IAM role, CloudWatch log groups, and four zone Lambdas (`ingest` / `silver` / `quality` / `gold`) from `build/lambda/lakehouse.zip`, with env vars from bucket/table/queue outputs. Ingest is subscribed to the Bronze SQS queue via event-source mapping. `make package` runs before `make infra`. S3/EventBridge object notifications are intentionally left for the next chore.

## 2026-08-28 23:00 IST
- Completed: feat: Pipeline run metadata & status tracking
- Next candidate: chore: Lambda packaging & deployment via Terraform (P0)
- Notes: Centralized DynamoDB run records in `lakehouse.pipeline.runs` (`new_run` / `complete_run` / `persist_run` / `get_run` / `list_runs`). Zone handlers (ingest, silver, quality, gold) and the local runner now share one item shape: run_id, status, zone, step, timestamps, error, objects, flattened metrics, quality JSON. `run_id` can be supplied via event payload or `LAKEHOUSE_RUN_ID` so steps stay correlated. CLI/Make: `python -m lakehouse runs` / `make runs`.

## 2026-08-28 21:00 IST
- Completed: feat: Quality gate as a first-class step
- Next candidate: feat: Pipeline run metadata & status tracking (P0)
- Notes: Added `lakehouse.quality.gate` (`evaluate_quality` with named checks, fail-ratio threshold, fail vs quarantine action) and `lakehouse.quality.handler` that reads Silver `events/`, writes a `quality/dt=.../run_id=....json` report, records DynamoDB run status (`quality_failed` when the gate fails), and optionally quarantines bad rows. Local path: `python -m lakehouse quality` / `make quality`. Pandera/GE remain optional; the default gate is Pydantic + explicit checks so Lambda zips stay small.

## 2026-08-28 20:00 IST
- Completed: feat: Gold aggregation Lambda
- Next candidate: feat: Quality gate as a first-class step (P0)
- Notes: Added `lakehouse.gold` — Lambda `handler` + `transform_gold` that reads Silver JSON (event-driven S3/SQS refs or batch list under `events/`), runs `aggregate_gold`, writes Hive-partitioned Gold JSON plus DynamoDB gold-metrics rows, and records run metadata. Local path: `python -m lakehouse gold` / `make gold`. Packaging the function as a Terraform Lambda zip remains the later chore.

## 2026-08-28 19:05 IST
- Completed: feat: Silver transform Lambda
- Next candidate: feat: Gold aggregation Lambda (P0) or feat: Quality gate as a first-class step (P0)
- Notes: Added `lakehouse.silver` — Lambda `handler` + `transform_silver` that reads Bronze JSON (event-driven S3/SQS refs or batch list), runs `cleanse_to_silver`, writes Hive-partitioned Silver JSON plus `quarantine/` objects, and records run metrics in DynamoDB. Local path: `python -m lakehouse silver` / `make silver`. Packaging the function as a Terraform Lambda zip remains the later chore.

## 2026-08-28 18:08 IST
- Completed: feat: Bronze event-driven ingestion via S3 → SQS → Lambda
- Next candidate: feat: Quality gate as a first-class step (P0) or chore: Lambda packaging & deployment via Terraform (P0)
- Notes: Added `lakehouse.ingest` — parse native S3 / SQS-wrapped S3 / EventBridge object refs, Lambda `handler` + `ingest_bronze_event` that HEAD/GETs Bronze objects under `events/` and writes a DynamoDB pipeline-run row. Terraform now creates `aws_sqs_queue.bronze_events` (notification wiring and Lambda zip remain later chores). Local drain: `python -m lakehouse ingest` / `make ingest`. Unit tests cover URL-decoded keys, skip of non-events prefixes, and missing-object failure.

## 2026-08-28 12:48 IST
- Completed: test: Expand unit tests for seed + transform
- Next candidate: feat: Bronze event-driven ingestion via S3 → SQS → Lambda (P0)
- Notes: Added `lakehouse.transforms.events` (parse/quarantine, late-event lookback, gold aggregate) plus `tests/test_seed.py` and `tests/test_transforms.py`.

## 2026-08-28 12:36 IST
- Completed: docs: Add ADR-003: Local orchestration vs Step Functions
- Next candidate: test: Expand unit tests for seed + transform (P0)
- Notes: Added `docs/adr/003-local-orchestration-vs-step-functions.md` (Accepted for v0.1).

## 2026-08-28 09:03 IST
- Completed: docs: Expand README with exact run instructions & screenshots
- Next candidate: docs: Add ADR-003: Local orchestration vs Step Functions (P0)

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
