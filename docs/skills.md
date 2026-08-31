# Skills demonstrated

Hiring-manager map of what this repo actually exercises. Every row
points at code, Terraform, tests, or a runbook — not a claim.

## How to evaluate in 15 minutes

1. Read this file and the [README](../README.md) value proposition.
2. Skim [ADR-003](adr/003-local-orchestration-vs-step-functions.md)
   (local runner vs Step Functions) and [ADR-002](adr/002-medallion-zones.md).
3. Run `python -m pip install -e ".[dev]" && make test` (no Docker).
4. If Docker is available: `make up && make infra && make demo`.
5. Open `TODO.md` / `PROGRESS.md` to see how work was sequenced.

The offline demo (`python -m lakehouse demo --mode offline`) is the
fastest proof that Bronze → quality → Gold plus assertions exist
without an AWS account.

## Skill matrix

| Skill | Evidence in the repo | Why it matters on a platform team |
| --- | --- | --- |
| Medallion modeling | `src/lakehouse/{ingest,silver,gold,transforms}/`, zone ADRs | Separates raw, cleansed, and serving grain instead of one blob bucket |
| Zone contracts | `configs/contracts/*.json`, `lakehouse.contracts`, `docs/data-dictionary.md` | Producers and consumers share a written schema, not tribal knowledge |
| Schema evolution / contract tests | `lakehouse.contract_check`, `tests/test_schema_evolution.py` | CI fails a producer that drops a required field or changes types |
| Data quality as a gate | `lakehouse.quality.gate`, quality Lambda, `docs/adr/004-quality-gate.md` | A bad batch fails the run or quarantines instead of silently landing in Gold |
| Event-driven ingest | S3 → SQS → ingest Lambda, `infra/terraform/notifications.tf` | Matches how object lakes actually wake up in AWS |
| Dead-letter + redrive | `lakehouse.ops.dlq`, `docs/dlq.md`, `make redrive` | Poison messages do not stall the queue forever |
| Orchestration | Local Python runner **and** Step Functions ASL (`sfn.asl.json.tftpl`) | Same zone functions, two drivers — see ADR-003 |
| Idempotency | Content hashes + deterministic keys (`pipeline/idempotency.py`) | Retries and SFN Catch paths do not double-count Gold |
| Late-arriving data | Lookback window, `make reprocess`, `docs/late-arriving.md` | Events that land after the daily cut still correct Gold |
| Run metadata | DynamoDB pipeline-runs (`run_id`, status, metrics, error) | Operators debug a failed date without tailing every Lambda log |
| Structured metrics | `lakehouse.metrics`, CloudWatch catalog, `docs/metrics.md` | Records processed, quality failures, lag — not just “it ran” |
| Analytics surface | Glue tables, Athena workgroup + named queries, dbt marts, query UI | Analysts query Gold grain, not raw JSON |
| Partition strategy | Hive keys + projection notes (`docs/partitions.md`) | Athena cost stays on Gold partitions, not full Bronze scans |
| Local-first AWS | MiniStack + endpoint-aware `lakehouse.aws` | Inner loop has no cloud bill; same Terraform aims at real AWS |
| Multi-environment IaC | `infra/terraform/envs/{local,aws}.tfvars`, ADR-006 | One module, two targets, documented flags |
| Operability | Makefile, JSON CLI, `docs/runbook.md` | Reprocess a date, inspect DLQ, dump SFN definition |
| Testing discipline | Hermetic unit suite + MiniStack integration marker | CI stays green without Docker; live path is opt-in |
| CI / pre-commit | `.github/workflows/ci.yml`, ruff, terraform fmt | Lint → unit → MiniStack loop as required checks |
| Security scanning | `lakehouse.security`, Checkov, Trivy, detect-secrets | Dummy MiniStack keys are allowlisted; live AKIA patterns fail tests |
| Cost awareness | `docs/cost-performance.md`, Athena bytes cap | Demo volume stays well under a dollar a month on real AWS |
| Documentation as product | ADRs, data dictionary, runbook, this file | Reviewers can reconstruct *why*, not only *what* |

## Role mapping

What a reviewer in each seat should look at first.

### Data engineer / analytics engineer

- Zone contracts and the quality gate (`configs/contracts/`, `quality/gate.py`).
- Silver cleanse + Gold daily grain (`transforms/events.py`, `gold/handler.py`).
- dbt project on Glue/Athena (`transform/dbt/`, `docs/analytical-model.md`).
- Late-arriving reprocess path.

### Data / platform engineer

- Terraform layout: buckets, queues, Lambdas, SFN, Glue/Athena flags.
- Endpoint-aware boto3 and MiniStack so local ≠ a second codebase.
- Idempotency keys, DLQ redrive, run table.
- CI that actually applies Terraform against MiniStack.

### Analytics / BI consumer

- Gold grain and KPIs in `docs/analytical-model.md`.
- Named Athena queries and `make ui` HTML snapshot.
- dbt marts: `fct_daily_event_metrics`, `fct_daily_purchase_revenue`,
  `dim_event_type`.

### Engineering manager

- Phased TODO with conventional-commit titles and a public `PROGRESS.md`.
- ADRs for the expensive choices (orchestration, quality, parquet/Glue).
- A one-command demo with assertions (`make demo`).
- CONTRIBUTING + CODEOWNERS so a new hire knows how to land a PR.

## What this is not

- Not a petabyte Spark cluster or Iceberg catalog.
- Not a multi-tenant SaaS control plane.
- Not a replacement for Great Expectations / Monte Carlo in production;
  the gate is Pandera-style and small on purpose.
- Streaming (Kinesis / Firehose) is still an optional Phase 5 item.

The scope is intentional: a **complete small lakehouse** — contracts,
quality, orchestration, catalog, CI — that a platform team can read in
an afternoon and run on a laptop.
