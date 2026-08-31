# Architecture Decision Records

ADRs capture choices that are expensive to reverse.

| ID | Title | Status |
| --- | --- | --- |
| [001](001-ministack-as-local-aws.md) | MiniStack as the local AWS control plane | Accepted |
| [002](002-medallion-zones.md) | Medallion zones on object storage | Accepted |
| [003](003-local-orchestration-vs-step-functions.md) | Local orchestration vs Step Functions | Accepted (runner v0.1; SFN in Phase 2) |
| [004](004-quality-gate.md) | In-process quality gate over a DQ platform | Accepted |
| [005](005-parquet-glue-athena.md) | Parquet on S3 + Glue/Athena query surface | Accepted |
| [006](006-multi-environment-terraform.md) | One Terraform root, two env files | Accepted |
| [007](007-idempotency-in-zone-functions.md) | Idempotency keys live in zone functions | Accepted |

`0003-*.md` is a longer draft of ADR-003 kept for history; the canonical
record is `003-*.md`.
