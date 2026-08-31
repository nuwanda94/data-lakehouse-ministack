# ADR-001: MiniStack as the local AWS control plane

- **Status:** Accepted
- **Date:** 2026-08-28
- **Deciders:** project maintainers
- **Related:** `docker-compose.yml`, `docs/environments.md`, ADR-006

## Context

The project needs a production-shaped AWS surface (S3, SQS, Lambda, DynamoDB,
Step Functions, Glue, Athena) that a laptop and GitHub Actions can run with
**zero cloud spend**. Three options were on the table:

1. **MiniStack** on `:4566` (open-source AWS emulator, Terraform-compatible).
2. **LocalStack** Community / Pro.
3. **Real AWS only** (dev account + tight IAM + budget alarms).

The stack must stay portable: the same Terraform and boto3 clients should
point at MiniStack today and at `amazonaws.com` later.

## Decision

**Use MiniStack as the default local and CI control plane.**

- Compose service listens on `http://localhost:4566`.
- Dummy credentials (`test` / `test`) are accepted locally.
- Real AWS is an explicit workspace (`ENV=aws`, `envs/aws.tfvars`), not the
  inner loop.
- Endpoint-aware clients live in `lakehouse.aws`; call sites never hard-code
  the MiniStack URL.

## Consequences

**Positive**

- Inner loop and CI have no AWS bill.
- Terraform apply against MiniStack is the same graph we would apply in AWS.
- Multi-account / multi-region emulator behaviour matches how we will later
  isolate `local` vs `aws` workspaces.

**Negative / accepted debt**

- Emulator fidelity is not 100%. Glue, Athena, and Step Functions need
  feature flags so `make infra` still works when a service is thin locally.
- Bugs that only exist in MiniStack (or only in AWS) will appear. Integration
  tests marked `integration` are the safety net, not a substitute for an
  occasional real-AWS apply.

## Alternatives considered

| Option | Why not |
| --- | --- |
| LocalStack as the default | Community surface has been shrinking; Pro is a paid dependency the project is trying not to take. MiniStack is MIT and Terraform-friendly. |
| Real AWS for every `make pipeline` | Defeats the "practice without a bill" goal; CI would need long-lived keys. |
| Moto-only (in-process) | Excellent for unit tests; not a substitute for Terraform + S3 event notifications + SQS. We already use hermetic tests *and* MiniStack. |

## Follow-ups

- Keep `FEATURE_*` flags for catalog / Athena / custom metrics so MiniStack
  gaps do not block Phase 0–2.
- Document emulator quirks in `docs/environments.md` as they are found.
