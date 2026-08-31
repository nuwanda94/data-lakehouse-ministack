# ADR-004: In-process quality gate over a separate DQ platform

- **Status:** Accepted
- **Date:** 2026-08-29
- **Deciders:** project maintainers
- **Related:** `src/lakehouse/quality/`, `docs/contracts.md`, `tests/test_schema_evolution.py`

## Context

Phase 1 requires a first-class quality step that can fail a run or quarantine
rows. Candidates:

1. In-process checks in `lakehouse.quality.gate` (schema, enums, nulls,
   ranges) driven by `configs/contracts/`.
2. **Pandera** DataFrame schemas as the implementation of those checks.
3. **Great Expectations** suites + docs site + optional GX Cloud.

## Decision

**Ship an in-process gate that reads zone contracts.** Pandera (or a thin
wrapper around it) is allowed as an implementation detail. Great Expectations
is out of scope for v1.

The gate must:

- run in the Python runner *and* the quality Lambda;
- write a structured result onto the DynamoDB run row;
- quarantine invalid rows rather than silently dropping them;
- fail the run when error rate exceeds the configured threshold.

Contract tests in CI (`make contracts`) catch producer drift before data
lands.

## Consequences

- No extra container, account, or HTML docs site to keep green in CI.
- Checks stay close to the transforms; reviewers can read one module.
- We do not get GX-style expectation galleries or data docs out of the box.
- If a hiring-manager demo needs a named library, swapping the gate internals
  to Pandera should not change the run-metadata contract.

## Alternatives considered

| Option | Why not now |
| --- | --- |
| Great Expectations first | Heavy runtime, cloud extras, and a second config language. Fine later as an optional adapter behind the same gate interface. |
| "Just pytest the fixtures" | Unit tests are necessary but do not quarantine live Bronze. |
| Fail-open (log and continue) | Teaches the wrong operational model; Gold would lie. |
