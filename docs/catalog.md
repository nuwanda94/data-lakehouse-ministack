# Glue Data Catalog — Silver and Gold

Phase 3 registers the medallion zones as Glue tables so Athena (next item)
can query them by name instead of raw S3 prefixes.

## Tables

| Glue table | Zone | Location | Partitions | Payload columns |
| --- | --- | --- | --- | --- |
| `lakehouse_local.commerce_event_conformed` | Silver | `s3://{silver}/events/` | `event_type`, `dt` | `event_id`, `event_ts`, `user_id`, `sku`, `quantity`, `amount_usd`, `country`, `_late` |
| `lakehouse_local.daily_event_metrics` | Gold | `s3://{gold}/metrics/` | `metric`, `dt` | `events`, `amount_usd` |

Hive types come from `configs/contracts/{silver,gold}.json`:

| Contract type | Glue / Hive type |
| --- | --- |
| string | string |
| integer | bigint |
| number | double |
| datetime | timestamp |
| date | date / string partition |
| boolean | boolean |

Gold's Hive key is `metric=` even though the JSON field is `event_type`. The
catalog keeps `metric` as the partition name so it matches objects under
`metrics/metric={event_type}/dt={date}/`.

v0.1 still writes **JSON** objects (Parquet-shaped keys). SerDe is
`org.openx.data.jsonserde.JsonSerDe`. A later change can swap classification
to Parquet without renaming columns.

## How tables are created

1. **Python (local-first).** `python -m lakehouse catalog` builds specs from
   the contracts and tries `glue.create_table` / `update_table`. If MiniStack
   has no Glue API the command still prints the full table definition
   (`backend=spec`).
2. **Terraform (real AWS).** `infra/terraform/glue.tf` defines the same
   database and tables. They are gated by `enable_glue` (default `false`) so
   `make infra` against MiniStack does not fail when Glue is missing.

```bash
# describe / best-effort register
make catalog
python -m lakehouse catalog

# real AWS
cd infra/terraform
terraform apply -var='enable_glue=true' -var='aws_endpoint_url='
```

## Changing a column

1. Edit `configs/contracts/silver.json` or `gold.json`.
2. Update `infra/terraform/glue.tf` comments/types to match.
3. Extend `tests/test_catalog.py` if a new required field is added.
4. Keep `docs/data-dictionary.md` in sync.

Partition projection (Athena workgroup + `projection.*` table parameters) is
the next Phase 3 chore after named Athena queries.
