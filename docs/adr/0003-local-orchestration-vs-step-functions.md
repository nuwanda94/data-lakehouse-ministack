# ADR-003: Local orchestration vs Step Functions

- **Status:** Accepted
- **Date:** 2026-08-28
- **Deciders:** project maintainers
- **Phase:** 0 (decision) → 2 (migration)

## Context

The lakehouse has two jobs that look similar but are not the same:

1. **Zone work** — read Bronze events, validate, write Silver, aggregate Gold,
   persist run metadata.
2. **Control plane** — decide *when* those steps run, in what order, with what
   retries, and how failures are surfaced.

Today the control plane is a synchronous Python runner
(`lakehouse.ops.pipeline.run_pipeline`, invoked by `make pipeline` /
`python -m lakehouse pipeline`). It walks S3, applies a quality stub, writes
Silver/Gold, and records a DynamoDB run row. That is enough to prove the
medallion path against MiniStack without standing up Lambda or Step Functions.

The target production shape (Phase 1–2) is event-driven: S3 object created →
SQS → Lambda per zone, with an explicit quality gate and run metadata. AWS
Step Functions (SFN) is the conventional control plane for that graph
(Map / Retry / Catch / Parallel).

We need an explicit decision so Phase 1 does not accidentally rebuild a
state machine inside the Python runner, and so Phase 2 has a clear trigger
for the cutover.

## Decision

**v0.1 (now through end of Phase 1): keep a local Python runner as the
control plane.**

- The runner is a *temporary orchestrator*, not the long-term product.
- Zone logic must live in importable functions (`lakehouse.pipeline.*`,
  `lakehouse.transforms.*`, `lakehouse.quality.*`) that a Lambda handler can
  call later without rewriting business code.
- The runner may sequence steps and persist run status. It must not grow
  custom retry graphs, fan-out executors, or a homegrown DAG engine.
- Local DX stays `make pipeline`. CI and demos use the same entrypoint.

**v0.2 (Phase 2): replace/augment the runner with a Step Functions state
machine** that invokes the same zone functions packaged as Lambdas.

The Python runner remains as:

- a fallback for laptops that only need a linear Bronze → Silver → Gold pass;
- a contract test harness (same inputs/outputs as SFN tasks);
- a way to exercise MiniStack when SFN coverage in the emulator is incomplete.

## Why start with the runner

| Factor | Python runner | Step Functions first |
| --- | --- | --- |
| Time-to-working-lakehouse | Hours | Days (ASL, IAM, packaging, emulator gaps) |
| Debuggability on a laptop | pdb, pytest, one process | distributed traces, payload size limits |
| MiniStack fidelity | S3 + DynamoDB is already proven here | SFN + Lambda + EventBridge need extra proving |
| Cost of being wrong | Delete a module | Tear down IAM + state machine + event wiring |
| Teaching the medallion model | Transforms stay in the foreground | Control-plane YAML dominates the diff |

Phase 0 exit criteria is `make up && make infra && make seed && make pipeline`
on a fresh machine. SFN does not help that criterion and would block it.

## Why move to Step Functions later

Once Bronze ingest is event-driven (S3 → SQS → Lambda), a single Python
process is the wrong control plane:

- **Retries and poison messages** belong in SQS visibility + SFN Retry/Catch,
  not in `for key in keys`.
- **Partial failure** (one date partition bad, others fine) needs Map + Catch,
  not an all-or-nothing runner.
- **Exactly-once / idempotency** is easier to reason about when each task has
  a name, input, and output in an execution history.
- **Real AWS cutover** should not invent a second orchestrator. SFN is the
  service we would run in `us-east-1`.
- **Observability** (execution ARN, failed state, redrive) is native to SFN.

## Alternatives considered

### 1. Step Functions from day one

Rejected for v0.1. Correct long-term shape, but it couples Phase 0 to Lambda
packaging, IAM, ASL, and emulator support before zone contracts are stable.

### 2. Airflow / Prefect / Dagster locally

Rejected. Extra runtime, extra mental model, and none of those are how this
stack would run on AWS. The project is explicitly *serverless medallion*, not
"another scheduler demo".

### 3. EventBridge Pipes / S3 notifications chaining Lambdas only

Possible as a thin Phase 1 wiring (Bronze write triggers Silver Lambda).
Kept as an option for *triggering* work, not as the full control plane.
Chained Lambdas hide retries, fan-out, and compensation. SFN still owns the
graph in Phase 2.

### 4. Keep the Python runner forever

Rejected for anything past a demo. It cannot express Map/Retry/Catch, does
not scale to late-arriving partitions, and teaches the wrong operational
model for a serverless lakehouse.

## Migration triggers (Phase 1 → Phase 2)

Start the SFN cutover when **all** of the following are true:

1. Bronze / Silver / Gold work is packaged as Lambdas (or the same handlers
   invoked in-process for tests).
2. Quality gate is a first-class step with a fail/quarantine outcome.
3. Run metadata (`run_id`, status, metrics, error) is written to DynamoDB
   independently of the orchestrator.
4. MiniStack (or the chosen local emulator) can start an SFN execution and
   invoke the Lambdas against the same buckets/tables.
5. The linear runner still passes as a contract test against the same zone
   functions.

Until then, new features go into zone modules, not into `ops/pipeline.py`.

## Consequences

**Positive**

- Phase 0/1 stay reviewable and testable without a state machine.
- Zone contracts can change without rewriting ASL.
- Cutover is a packaging + wiring change, not a rewrite of transforms.

**Negative / accepted debt**

- Two control planes will exist briefly (runner + SFN).
- The runner will look "good enough" and may attract features it should not
  own. Reviewers should reject PRs that add retry graphs there.
- Local SFN parity with AWS may lag; the runner is the safety net.

## Operational notes

- Document how to reprocess a date in the Phase 2 runbook. Until SFN exists,
  reprocess = `make seed` (or put objects) + `make pipeline`.
- Execution identity today is `run_id` from `lakehouse.pipeline.runs`.
  SFN will add `execution_arn`; store both when the state machine lands.
- Idempotency keys (Phase 2 P1) must be computed *inside zone functions*,
  not inside the orchestrator, so both runners stay correct.

## References

- Implementation plan Phase 0 docs item: *ADR-003: Local orchestration vs Step Functions*
- Implementation plan Phase 2 feat: *Step Functions state machine*
- Current runner: `src/lakehouse/ops/pipeline.py`
- README architecture section ("Python runner v0.1" / "Step Functions in Phase 2")
