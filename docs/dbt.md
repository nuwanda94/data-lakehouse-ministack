# dbt on Athena / Glue

Phase 3 P2 adds a small dbt project on top of the Glue Silver / Gold
tables. It does **not** replace the Python pipeline. Gold objects are
still written by `lakehouse.gold.handler`; dbt only models what Athena
already sees.

## Layout

```
transform/dbt/
  dbt_project.yml
  profiles.yml.example
  models/
    sources.yml          # Glue lakehouse_local.{silver,gold}
    schema.yml           # tests + docs
    staging/stg_daily_event_metrics.sql
    marts/fct_daily_event_metrics.sql
    marts/fct_daily_purchase_revenue.sql
    marts/dim_event_type.sql
```

| Model | Grain | Source |
| --- | --- | --- |
| `stg_daily_event_metrics` | `event_type` x `dt` | source `lakehouse.daily_event_metrics` (`metric` renamed) |
| `fct_daily_event_metrics` | same | staging |
| `fct_daily_purchase_revenue` | `dt` (purchase only) | staging `where event_type = 'purchase'` |
| `dim_event_type` | 1 row per contract enum | distinct staging `event_type` |

KPI definitions stay in [`analytical-model.md`](analytical-model.md).
Named Athena queries stay in `lakehouse.athena.named_queries()`.

## Local (no Athena)

MiniStack usually has no Athena API. Parse and lint the project without
dbt-core:

```bash
python -m lakehouse dbt
make dbt
```

That command loads YAML + SQL, compiles `{{ source }}` / `{{ ref }}`
against `lakehouse_local`, and fails if models drift from the Glue
catalog names.

## Real AWS

1. Glue tables exist (`enable_glue=true` / `make catalog`).
2. Athena workgroup exists (`enable_athena=true`).
3. Install an Athena adapter (not a runtime dependency of this package):

```bash
pip install dbt-core dbt-athena-community
cp transform/dbt/profiles.yml.example ~/.dbt/profiles.yml
# edit s3_staging_dir / work_group if your tfvars differ
cd transform/dbt
dbt debug --target athena
dbt run --target athena
dbt test --target athena
dbt docs generate --target athena
```

Keep `work_group: lakehouse-local` so the 100 MiB scan cap still applies
([`docs/athena.md`](athena.md), [`docs/cost-performance.md`](cost-performance.md)).
Query Gold marts, not Bronze.

## Change control

- New Gold measures -> contract + handler + Glue + Athena **and** dbt
  staging/marts + `schema.yml`.
- Breaking grain changes -> ADR.
- `tests/test_dbt.py` asserts the four models and Glue source names.
