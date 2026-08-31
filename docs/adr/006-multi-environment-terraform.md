# ADR-006: One Terraform root, two env files

- **Status:** Accepted
- **Date:** 2026-08-30
- **Deciders:** project maintainers
- **Related:** `docs/environments.md`, `infra/terraform/envs/`, `lakehouse.environments`

## Context

Phase 4 needs local MiniStack and real AWS from the same codebase. Options:

1. **One root module** + `envs/local.tfvars` / `envs/aws.tfvars` + optional
   workspaces (`make infra ENV=local|aws`).
2. Two roots / two repos ("local stack" vs "prod stack").
3. Terragrunt or a full env-per-directory layout.

## Decision

**Keep a single `infra/terraform` root.**

- `ENV=local` (default): MiniStack endpoint, dummy keys, catalog flags off.
- `ENV=aws`: real AWS endpoints, caller credentials, no MiniStack health
  gate.
- Provider configuration is the only substantial branch; resource names stay
  parameterized.
- Python settings resolve endpoint + resource names from process env,
  generated outputs, then defaults — never from a second code path.

## Consequences

- Reviewers see one graph. Drift between "the demo" and "the real thing" is
  harder to hide.
- State files must not be mixed: local state stays on disk; AWS state should
  move to S3/DynamoDB before anyone applies from two laptops.
- A bad `ENV` mix (aws tfvars against MiniStack, or dummy keys against AWS)
  is a foot-gun. `python -m lakehouse env` and the Makefile health short-
  circuit exist to catch that.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Two roots | Guarantees drift; doubles every resource change. |
| Terragrunt | Extra wrapper for two files of tfvars. |
| Separate GitHub repo for AWS | Kills the "same code" claim. |
