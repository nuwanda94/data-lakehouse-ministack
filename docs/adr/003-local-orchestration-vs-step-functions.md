# ADR-003: Local orchestration vs Step Functions

- **Status:** Accepted (for v0.1); revisit at Phase 2
- **Date:** 2026-08-28
- **Deciders:** project maintainers
- **Related:** Phase 0 foundation, Phase 1 zone Lambdas, Phase 2 reliability

## Context

The lakehouse has three processing zones (Bronze → Silver → Gold), a quality
gate, and DynamoDB run metadata. Something has to sequence those steps,
retry them, and record success or failure.

Two reasonable options exist:

1. A **local Python runner** (`python -m lakehouse pipeline` /
   `lakehouse.ops.pipeline.run_pipeline`) invoked by Make or CI.
2. An **AWS Step Functions** state machine (Map / Retry / Catch / Parallel)
   that invokes per-zone Lambdas.

The README already states the intended end state: the control plane starts
as a Python runner and moves to Step Functions in Phase 2. This record
makes that choice explicit so later PRs do not accidentally invent a third
orchestrator.

Constraints that matter:

- The stack must run on MiniStack (`http://localhost:4566`) with no AWS bill.
- Terraform and Python should stay portable to real AWS.
- MiniStack Step Functions coverage is improving but is not the fastest
  inner-loop tool for iterating on transforms and quality checks.
- Zone work itself (parse, validate, write Parquet/JSON, emit metrics) must
  live in library code that either the runner or a Lambda handler can call.

## Decision

**v0.1 (Phase 0–1): orchestrate with the Python runner.**

- `make pipeline` / `python -m lakehouse pipeline` is the only supported
  control plane.
- Zone logic stays in `lakehouse.pipeline` and `lakehouse.transforms` so it
  can be imported by future Lambda handlers without rewriting the graph.
- Run identity (`run_id`, status, quality results) is written to DynamoDB
  by the runner. That contract is the same one Step Functions will later
  update from Task states.
- Event-driven *ingest* (S3 → SQS → Lambda) is still in scope for Phase 1.
  That is a trigger, not an orchestrator. The runner remains how a full
  Bronze → Gold pass is started until Phase 2.

**Phase 2: replace/augment the runner with a Step Functions definition.**

Move when *all* of the following are true:

1. Bronze, Silver, Gold, and the quality gate exist as invocable units
   (Lambda handlers wrapping the same library functions).
2. A run can be identified and resumed from DynamoDB (`run_id` + zone).
3. We need production semantics the runner cannot honestly claim:
   per-state Retry/Catch, Map over partitions, Parallel quality + write,
   visual execution history, or IAM-isolated task roles.
4. MiniStack (or a real AWS account used in a workspace) can execute the
   ASL definition we check in under `infra/terraform`.

Until then, do **not** add Airflow, Prefect, Dagster, Glue Workflows, or a
hand-rolled state machine in DynamoDB.

## Consequences

### Positive

- Inner loop stays one command and works offline against MiniStack.
- Transforms and quality checks are unit-testable without mocking ASL.
- The same functions become Lambda handlers later; orchestration is a
  thin layer above them.
- Failure modes are obvious: the CLI raises, the run row is
  `quality_failed` or `succeeded`.

### Negative / accepted debt

- No visual execution graph or managed retries until Phase 2.
- The runner is a single process: a crash mid-zone is not a clean Catch.
- CI must invoke the runner (or later `aws stepfunctions start-execution`)
  rather than a cloud-native trigger alone.
- We must keep the runner and the future SFN graph aligned so they do not
  diverge on zone order or quality-gate behaviour.

### Migration sketch (not implemented here)

```text
                    +------------------+
  S3/SQS/manual --> | Start            |
                    +--------+---------+
                             v
                    +------------------+
                    | Bronze ingest    |  Lambda + Retry
                    +--------+---------+
                             v
                    +------------------+
                    | Quality gate     |  Fail -> Catch -> status=quality_failed
                    +--------+---------+
                             v
                    +------------------+
                    | Silver transform |
                    +--------+---------+
                             v
                    +------------------+
                    | Gold aggregate   |
                    +--------+---------+
                             v
                    +------------------+
                    | Record succeeded |
                    +------------------+
```

The Python runner today is that graph inlined in
`lakehouse.ops.pipeline.run_pipeline`. Phase 2 should extract each box,
not invent a different sequence.

## Alternatives considered

| Option | Why not now |
| --- | --- |
| Step Functions from day one | Slower local loop; harder unit tests; MiniStack SFN is not required to prove the medallion transforms. |
| EventBridge → chained Lambdas | Implicit graph, weak fan-in, easy to lose run_id. Fine as a *trigger*, not as the orchestrator. |
| Glue Workflows / MWAA / Prefect | Extra runtime and cost; fights the serverless + MiniStack goal. |
| Make-only recipes with no Python runner | Make is a convenience wrapper. Logic belongs in importable Python. |

## Follow-ups

- Phase 1: Lambda packaging + S3/SQS trigger; keep calling the same zone functions.
- Phase 2: check in an ASL definition and Terraform `aws_sfn_state_machine`; keep `make pipeline` as a local shim that either runs the library graph or starts the state machine.
- Docs: update the README architecture diagram when the SFN path lands.
