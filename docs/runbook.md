# Runbook: reprocess a date and debug a failed run

Operator path for the local MiniStack lakehouse. Zone behaviour is unchanged;
this document is how to *find* a bad run and *safely* rebuild Gold.

Related references:

- Late windows: [`docs/late-arriving.md`](late-arriving.md)
- Idempotent retries: [`docs/idempotency.md`](idempotency.md)
- Bronze DLQ: [`docs/dlq.md`](dlq.md)
- SFN graph: [`docs/sfn.md`](sfn.md)
- Failure modes: [`docs/failure-injection.md`](failure-injection.md)
- Knobs: [`docs/configuration.md`](configuration.md)

## 0. Preconditions

```bash
make health          # MiniStack :4566 + S3/DynamoDB reachable
make outputs         # confirm bucket / queue / table names
python -m lakehouse settings
```

If health reports errors, fix MiniStack (`make up`, `make logs`) before
reprocessing. Stale shell env (`BRONZE_BUCKET=...`) overrides Terraform
outputs — start from a clean terminal or `eval "$(make outputs)"`.

## 1. Detect a failed or stale run

```bash
make runs            # DynamoDB pipeline-runs
make query           # Gold objects + gold-metrics rows
make dlq             # poison Bronze events
```

Look at each run item:

| Field | What it tells you |
| --- | --- |
| `run_id` | Deterministic `{zone}-{digest}` (see idempotency) |
| `zone` / `step` | `ingest`, `silver`, `quality`, `gold`, `reprocess` |
| `status` | `succeeded`, `failed`, `quality_failed`, `running` |
| `metrics.idempotency_key` | Fingerprint of the object set |
| `metrics.missing` / error text | Bronze object gone, parse failure, gate fail |
| `idempotent_replay` | Handler skipped writes because this key already succeeded |

A quality gate that does not pass records `status=quality_failed` (or
`passed=false`) and **does not invoke Gold**. That is expected, not a
Gold bug.

## 2. Classify the failure

Work top-down. Stop at the first match.

### A. Poison / missing Bronze event

Symptoms: ingest `status=failed`, `missing` keys, or messages on the DLQ.

```bash
make dlq
# Fix or drop the bad object in lakehouse-local-bronze, then:
make redrive         # DLQ → bronze-events
make ingest          # drain the source queue again
```

If the Bronze object is gone, re-seed or put the file back first.
Redrive of a missing key will fail again (same fingerprint) until the
object exists — that is intentional.

### B. Schema drift / quarantine

Symptoms: Silver run succeeded with quarantined rows, or quality
`passed=false`.

```bash
make quality         # re-run the gate against current Silver
python -m lakehouse settings   # QUALITY_ON_FAIL, QUALITY_MAX_FAIL_RATIO
```

- `QUALITY_ON_FAIL=fail` (default): stop before Gold.
- `QUALITY_ON_FAIL=quarantine`: allow Gold on the clean subset.

Do not raise `QUALITY_MAX_FAIL_RATIO` to "make CI green" without fixing
the producer. Contracts live in `configs/contracts/`.

### C. Zone Lambda / SFN Catch

Symptoms: `make sfn` ends `Failed`; later zones never ran.

```bash
make sfn-def         # inspect the graph
make ingest && make silver && make quality && make gold
# or the local interpreter:
make sfn
```

Each Task retries 3 times then Catch → `Failed`. Re-run the *failed*
zone after the underlying object exists; succeeded zones with the same
object set replay instead of rewriting.

### D. Late events / Gold under-count

Symptoms: Gold for `dt=YYYY-MM-DD` is missing rows that now sit in Silver
with `_late=true`.

This is not a failed run. Use the reprocess path in section 3.

## 3. Reprocess a date (Gold rebuild)

`make reprocess` rebuilds Gold from **all** Silver events in the lookback
window, not just the late rows. Partial overwrites would under-count.

Default window is inclusive `[today - LOOKBACK_DAYS, today]` (UTC).

```bash
# Last LOOKBACK_DAYS (default 2) through now UTC
make reprocess

# Explicit window end + width
LOOKBACK_DAYS=7 AS_OF=2026-01-10 make reprocess
python -m lakehouse reprocess --lookback-days 7 --as-of 2026-01-10
```

What it does:

1. Lists Silver keys under `events/` whose Hive `dt=` is in the window.
2. Aggregates each `(event_type, dt)` from the full partition.
3. Puts the Gold object and the `gold-metrics` DynamoDB row.
4. Writes a `zone=gold` / `step=reprocess` pipeline-run item.

A second reprocess of the **same Silver keys** keeps the same `run_id`
and is an idempotent replay if the first one succeeded.

### Rebuild a single calendar day

Set `AS_OF` to that day and `LOOKBACK_DAYS=0`:

```bash
LOOKBACK_DAYS=0 AS_OF=2026-01-08 make reprocess
```

That window is `[2026-01-08, 2026-01-08]`.

### After reprocess

```bash
make query
make runs
```

Confirm the Gold object for that `dt` and a `step=reprocess` run with
`status=succeeded`.

## 4. Full zone replay (when Silver itself is wrong)

Reprocess only rebuilds Gold from current Silver. If Silver is stale or
quarantined incorrectly:

```bash
make ingest          # drain new Bronze / redriven messages
make silver          # rewrite Silver from Bronze
make quality
make gold            # first-write of the current Silver batch
make reprocess       # merge any late partitions the batch touched
```

Prefer `make sfn` when you want the Phase 2 order (ingest → silver →
quality → choice → gold) instead of invoking zones by hand.
`make pipeline` is the v0.1 Python runner (ADR-003) and is still valid
for a clean demo loop.

## 5. Do not

- Do not delete a *succeeded* DynamoDB run to force a rewrite of the same
  object set. Change the object set (new key or fixed content) or use
  `reprocess` (different `step`, same Gold merge semantics).
- Do not raise lookback to "the whole lake" on MiniStack without checking
  object count; the local runner loads the window into process memory.
- Do not treat `idempotent_replay=true` as a silent no-op failure. The
  previous success still stands; inspect `make query`.

## 6. Quick map

| Goal | Command |
| --- | --- |
| See run history | `make runs` |
| See Gold totals | `make query` |
| Peek poison events | `make dlq` |
| Restore poison events | `make redrive` then `make ingest` |
| Rebuild Gold for N days | `LOOKBACK_DAYS=N make reprocess` |
| Rebuild Gold for one `dt` | `LOOKBACK_DAYS=0 AS_OF=YYYY-MM-DD make reprocess` |
| Walk the SFN graph locally | `make sfn` |
