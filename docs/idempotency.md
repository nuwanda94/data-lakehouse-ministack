# Idempotency keys and exactly-once effects

Delivery is still at-least-once (SQS visibility timeout, DLQ redrive, SFN
Retry). Processing is made idempotent so a retry of the *same content*
does not mint a second pipeline identity or rewrite a succeeded run.

## How a key is built

```
idempotency_key = "{zone}#" + sha256(zone + sorted(object keys + missing markers))
run_id          = "{zone}-" + first 16 hex chars of that digest
```

Object keys are the accepted Bronze or Silver paths. Missing objects are
included as `missing:{bucket}/{key}` so a failed lookup stays stable
across retries until the object appears (at which point the fingerprint
changes and a new run is allowed).

Zone prefixes keep Bronze / Silver / Gold from colliding when they hash
the same filenames.

## Replay rule

1. Compute the deterministic `run_id`.
2. `GetItem` that row from `PIPELINE_RUNS_TABLE`.
3. If `status == succeeded`, return `idempotent_replay=true` and skip
   writes.
4. Failed / running / missing rows are processed again and overwrite the
   same `run_id`.

Handlers stamp `metrics.idempotency_key` on the run item so operators can
join retries in `make runs`.

## What this is not

This is **not** a distributed lock. Concurrent first-time executions of
the same key can both write; the last PutItem wins. That is acceptable
for MiniStack and the current Lambda concurrency of one ingest mapping
batch. A later chore can add a conditional `attribute_not_exists(run_id)`
claim if real-AWS parallelism needs it.
