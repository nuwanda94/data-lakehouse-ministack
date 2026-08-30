# Zone contracts

Machine-readable contracts for Bronze, Silver, Gold, the quality gate, and
pipeline-run metadata. Human-readable companions:
[`docs/data-dictionary.md`](../../docs/data-dictionary.md) (fields) and
[`docs/analytical-model.md`](../../docs/analytical-model.md) (grain and KPIs).

| File | Zone / surface |
| --- | --- |
| [`bronze.json`](bronze.json) | Raw commerce events (`events/dt=…`) |
| [`silver.json`](silver.json) | Conformed events + quarantine |
| [`gold.json`](gold.json) | Daily metrics + DynamoDB gold-metrics |
| [`quality.json`](quality.json) | Named quality checks + report object |
| [`pipeline_run.json`](pipeline_run.json) | DynamoDB pipeline-runs item |

These files are the source of truth for field names and partition keys.
`lakehouse.models.CommerceEvent`, `tests/test_contracts.py`, and
`tests/test_schema_evolution.py` must stay aligned with them.
`python -m lakehouse contracts` / `make contracts` fails a PR that
changes a producer without updating the matching contract. Compatibility
rules live in [`docs/contracts.md`](../../docs/contracts.md).
