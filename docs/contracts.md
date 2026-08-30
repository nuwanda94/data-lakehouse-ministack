# Schema evolution and contract testing

Zone contracts in [`configs/contracts/`](../configs/contracts/) are the
source of truth for field names, types, enums, and partition keys. CI
treats a producer that drifts from those files as a failed check.

## What the check covers

`python -m lakehouse contracts` (also `make contracts`) does three things:

1. **Document shape** — every `*.json` has a name, unique fields, known
   types, and well-formed enums.
2. **Producer alignment** — `CommerceEvent`, seed `EVENT_TYPES`, quality
   gate check names, Gold measures, and `PipelineRun` fields must match
   the contracts.
3. **Payload validation** — a sample of generated Bronze events must
   satisfy the Bronze field list (required, type, enum).

The same helpers live in `lakehouse.contracts`:

| Helper | Use |
| --- | --- |
| `validate_contract_document` | lint one JSON document |
| `validate_payload` | check a producer row against a contract |
| `compare_contracts(old, new)` | classify a proposed change as breaking vs additive |
| `check_all` | documents + producers (what the CLI runs) |

## Compatibility rules

**Breaking** (fail a PR unless you intend a versioned cut):

- remove a required field
- add a new required field
- change a type except along the widen lattice (`integer` → `number`,
  `date` → `datetime`/`string`)
- remove an enum value
- add an enum to a previously unconstrained field
- change Hive partition keys
- drop a named quality check

**Additive** (safe):

- add an optional field
- add an enum value
- drop an optional field
- make a required field optional
- widen a type along the lattice above

## How to change a contract

1. Edit the JSON under `configs/contracts/`.
2. Update the producer (`CommerceEvent`, seed enums, quality checks,
   Gold handler, Glue comments) in the same PR.
3. If the change is breaking, say so in the PR and update
   [`analytical-model.md`](analytical-model.md) / the data dictionary.
4. Run `make contracts` and `make test` — `tests/test_schema_evolution.py`
   covers the rules above with in-memory diffs, so you do not need a
   second copy of each JSON file.

There is no separate snapshot file. The checked-in contracts *are* the
current schema; evolution is tested by `compare_contracts` against
synthetic before/after documents.
