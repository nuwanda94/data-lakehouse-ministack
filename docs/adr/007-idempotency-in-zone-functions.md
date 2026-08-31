# ADR-007: Idempotency keys live in zone functions

- **Status:** Accepted
- **Date:** 2026-08-29
- **Deciders:** project maintainers
- **Related:** `docs/idempotency.md`, `docs/dlq.md`, `docs/late-arriving.md`, ADR-003

## Context

S3 events, SQS redeliveries, Step Functions retries, and `make reprocess`
will all hit the same zone more than once. Exactly-once *processing* is not
something SQS can promise. We need deterministic outputs.

## Decision

**Compute idempotency keys inside zone functions, not in the orchestrator.**

- Bronze object identity is the S3 key + content hash of the payload.
- Silver / Gold output keys are derived from event date + grain, so a retry
  overwrites the same object rather than appending a sibling.
- DynamoDB run rows use `run_id` (and later `execution_arn`) as the
  control-plane key; they record status, they do not define object names.
- DLQ redrive replays the original message; the zone function must tolerate
  that.

The Python runner and the Step Functions graph therefore stay interchangeable
without double-writing Gold.

## Consequences

- Late-arriving data is a *lookback rewrite* of Gold (`LOOKBACK_DAYS`), not
  a new measure row per attempt.
- Callers must not invent output keys. If a new partition scheme is needed,
  change the zone function and the contract together.
- True exactly-once side effects (email, webhooks) are out of scope; this
  decision only covers lake objects and run metadata.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Orchestrator-assigned UUIDs per attempt | Multiplies Gold objects; breaks Athena partition projection. |
| FIFO SQS + content dedup only | Helps ingest; does not cover `make reprocess` or SFN Retry. |
| Iceberg MERGE | Right tool at larger scale; not required for daily grain demo data. |
