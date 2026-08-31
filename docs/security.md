# Security scanning

Three scanners cover IaC, filesystem secrets, and a hermetic repo check that
runs in unit tests without Docker or extra CLIs.

| Tool | What it covers | How to run |
| --- | --- | --- |
| Hermetic `lakehouse.security` | AWS key / PEM / GitHub / Slack patterns | `python -m lakehouse security` or `make test` |
| [Checkov](https://www.checkov.io/) | Terraform in `infra/terraform` | `checkov -d infra/terraform --config-file .checkov.yaml` |
| [Trivy](https://trivy.dev/) | Secrets + HIGH/CRITICAL FS findings | `trivy fs --config trivy.yaml --scanners secret .` |
| detect-secrets (optional) | Broader entropy / keyword scan | `detect-secrets scan --baseline .secrets.baseline` |

`make security` runs the hermetic scan always, then Checkov and Trivy when
those binaries are on `PATH`. CI installs Checkov and uses `trivy-action`.

## Why some Checkov checks are skipped

`.checkov.yaml` skips controls that fight the MiniStack loop:

- S3 versioning, access logs, KMS, replication — buckets are ephemeral and
  `force_destroy` is required so `make clean` works.
- DynamoDB PITR / CMK and SQS encryption — dummy local tables/queues.
- Lambda VPC / X-Ray — not available (or not worth the cold start) on MiniStack.

Those skips are **local-only**. Before `ENV=aws`, turn the relevant checks
back on (or add the matching Terraform resources) rather than copying the
skip list into a production root module.

## Dummy credentials

`.env.example` uses MiniStack's documented dummy pair (`test` / `test`).
The hermetic scanner allowlists those values. A real `AKIA…` key or a PEM
block fails `make test` and the `security` CI job.

## Adding an accepted finding

1. Confirm it cannot be fixed in the same PR.
2. Record the Checkov/Trivy ID and the reason in this file.
3. Add the ID to `.checkov.yaml` `skip-check` or `.trivyignore`.
4. Do not baseline a live cloud credential.
