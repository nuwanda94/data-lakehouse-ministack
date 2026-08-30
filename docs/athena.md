# Athena workgroup and named queries

Phase 3 adds a cost-capped Athena workgroup and four named queries over the
Glue Silver / Gold tables from `docs/catalog.md`.

## Workgroup

| Setting | Value |
| --- | --- |
| Name | `lakehouse-local` |
| Result location | `s3://{gold}/athena-results/` |
| Bytes scanned cutoff | 100 MiB per query |
| Enforce workgroup config | true (callers cannot override result location) |
| CloudWatch metrics | enabled |

The cutoff is a local-first cost control. Raise it in Terraform / Python
together when Gold grows.

## Named queries

| Name | Intent |
| --- | --- |
| `gold_daily_totals` | All Gold rows (`metric`, `dt`, `events`, `amount_usd`) |
| `gold_purchase_revenue` | Purchase-only Gold (revenue proxy) |
| `gold_last_7_days` | Gold rows for the last 7 calendar days |
| `silver_late_event_counts` | Silver late vs on-time counts by `event_type`, `dt` |

SQL is the source of truth in `lakehouse.athena.named_queries()` and is
copied into `infra/terraform/athena.tf`. Tests assert the names and table
references stay in sync.

## How it is created

1. **Python (local-first).** `python -m lakehouse athena` prints the
   workgroup spec and tries `CreateWorkGroup` / `CreateNamedQuery`. MiniStack
   usually has no Athena API; the command still exits 0 with
   `backend=spec`.
2. **Run a named query.** `python -m lakehouse athena --name gold_daily_totals`
   calls `StartQueryExecution` when Athena is reachable; otherwise it prints
   the SQL.
3. **Terraform (real AWS).** Gated by `enable_athena` (default `false`) so
   `make infra` against MiniStack does not fail.

```bash
make athena
python -m lakehouse athena
python -m lakehouse athena --name gold_purchase_revenue

cd infra/terraform
terraform apply -var='enable_glue=true' -var='enable_athena=true' -var='aws_endpoint_url='
```

Athena needs the Glue tables from `make catalog` / `enable_glue=true` plus
partition projection ([`docs/partitions.md`](partitions.md)) for cheap partition pruning without `MSCK REPAIR TABLE`.
