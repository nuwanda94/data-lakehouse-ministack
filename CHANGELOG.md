# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and version numbers follow [SemVer](https://semver.org/spec/v2.0.0.html).

How to cut a release: [`docs/release.md`](docs/release.md).

## [Unreleased]

### Added

- Optional Kinesis / Firehose streaming path (`python -m lakehouse stream`,
  `make stream`, gated Terraform in `infra/terraform/streaming.tf`).
- Shared-library extract across zone handlers (`lakehouse.storage`).
- Dataset lineage snapshot (`python -m lakehouse lineage`, `make lineage`).
- Gold freshness SLA (`python -m lakehouse sla`, `make sla`).
- Gold partition retention (`python -m lakehouse retention`, `make retention`).
- Silver quarantine TTL (`python -m lakehouse quarantine-retention`,
  `make quarantine-retention`).
- Bronze raw object retention (`python -m lakehouse bronze-retention`,
  `make bronze-retention`).
- Silver cleaned-event retention (`python -m lakehouse silver-retention`,
  `make silver-retention`).
- Gold compact-after-retention (`python -m lakehouse maintain`, `make maintain`).
- Bronze raw-object compact (`python -m lakehouse bronze-compact`,
  `make bronze-compact`).

## [0.1.0] - 2026-09-01

Working lakehouse on MiniStack: Bronze → Silver → Gold with quality,
orchestration, catalog, CI, and a one-command demo.

### Added

- Installable `src/lakehouse` package, Makefile loop, MiniStack Compose stack.
- Terraform for S3 zones, DynamoDB run/metrics tables, Lambdas, SQS + DLQ,
  Step Functions, optional Glue / Athena.
- Event-driven Bronze ingest (S3 → SQS → Lambda) and Silver / Gold handlers.
- Quality gate (Pandera-style contracts) that can fail or quarantine a run.
- Pipeline run metadata in DynamoDB (`run_id`, status, metrics, errors).
- Idempotency keys, late-arriving lookback, `make reprocess`, DLQ redrive.
- Glue catalog views, Athena workgroup + named queries, dbt Gold marts.
- Offline-capable query UI (`make ui`) and `notebooks/gold_query.ipynb`.
- One-command demo (`make demo` / `python -m lakehouse demo`) with assertions.
- Multi-environment tfvars (`local` / `aws`), cost notes, structured metrics.
- Hermetic security scan plus Checkov / Trivy wiring.
- CONTRIBUTING, CODEOWNERS, ADRs, runbook, skills map.

### Documentation

- README value proposition, architecture diagram, status table.
- Zone contracts and data dictionary under `configs/contracts/` and `docs/`.

[Unreleased]: https://github.com/nuwanda94/data-lakehouse-ministack/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/nuwanda94/data-lakehouse-ministack/releases/tag/v0.1.0
