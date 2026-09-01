# ADR-008: Optional Kinesis / Firehose path into Bronze

Status: Accepted
Date: 2026-09-01

## Context

The lakehouse already has a batch producer (`make seed`) and an
event-driven Bronze ingest path (S3 → SQS → Lambda). The implementation
plan listed an optional streaming path (Kinesis / Firehose) as Phase 5
P2. MiniStack emulates both services, but CI and first-run `make infra`
must stay reliable when those APIs are incomplete or unused.

## Decision

Add a **sidecar producer**, not a replacement for seed:

- Encode the same `CommerceEvent` records as Kinesis and Firehose
  payloads.
- Land them on the existing Bronze Hive prefix so Silver / quality /
  Gold stay unchanged.
- Keep Terraform resources behind `enable_streaming` (default `false`).
- Ship a hermetic offline backend so unit tests and `python -m
  lakehouse stream --mode offline` never need Docker.

## Consequences

- Streaming is a documented optional skill demo, not a required control
  plane dependency.
- Live PutRecords / PutRecordBatch failures are recorded, not fatal,
  because Bronze writes still feed the medallion path.
- Enabling the Terraform module on real AWS still needs encryption,
  monitoring, and buffering review (see Checkov skips).
