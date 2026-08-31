# Cost and performance notes

Local MiniStack is free (Docker CPU/RAM only). These notes apply when
`ENV=aws` points the same Terraform at a real account. Prices are
**us-east-1 order-of-magnitude estimates** (on-demand, mid-2026 public
list). Treat them as planning bounds, not an invoice.

Related: [`environments.md`](environments.md), [`metrics.md`](metrics.md)
(`EstimatedBytes` cost proxy), [`athena.md`](athena.md) (scan cutoff),
[`partitions.md`](partitions.md).

## What actually bills on AWS

| Service | How this project uses it | Typical driver |
| --- | --- | --- |
| S3 | Bronze JSON, Silver/Gold Parquet-shaped objects, Athena results | Storage + PUT/GET |
| Lambda | ingest / silver / quality / gold handlers | Invocations + GB-seconds |
| SQS | Bronze event queue + DLQ | Requests (cheap) |
| DynamoDB | `pipeline-runs`, `gold-metrics` (on-demand) | WRU/RRU |
| Step Functions | Medallion state machine (Phase 2) | State transitions |
| Glue Data Catalog | Silver + Gold tables | Storage is free at this scale; crawlers unused |
| Athena | Named queries over Gold / Silver | **Bytes scanned** |
| CloudWatch | Logs + optional custom metrics | Log ingest + metric cardinality |
| SSM | Centralized config parameter | Negligible |

Glue / Athena stay **off** on MiniStack (`enable_glue` / `enable_athena`
false). Do not enable them locally and expect a cloud bill — there is none
until `ENV=aws`.

## Worked example (demo volume)

Assume one `make seed --count 50` + one full Bronze → Silver → Gold run
per day, 30 days, objects ~2 KiB Bronze / ~8 KiB Gold (same constants as
`EstimatedBytes` in `docs/metrics.md`).

| Line item | Monthly estimate | Why it is tiny |
| --- | --- | --- |
| S3 storage | ≪ $0.01 | Tens of objects, kilobytes |
| S3 API | ≪ $0.01 | Hundreds of PUT/GET |
| Lambda (4 fn × 30 runs, 256 MB, 1–2 s) | ≪ $0.02 | Far below the free-tier-shaped floor |
| SQS | ≪ $0.01 | One message per Bronze object |
| DynamoDB on-demand | ≪ $0.02 | One run row + a few metric rows / day |
| Step Functions | ≪ $0.02 | ~10 transitions / run |
| Athena (Gold-only, partition pruned) | ≪ $0.01 | Gold is already aggregated |
| CloudWatch logs | $0.01–0.10 | Keep retention short |

**Demo / portfolio AWS spend should stay under a dollar a month** if you
do not point Athena at Bronze and do not leave high-cardinality custom
metrics on.

Scale check: 1 million Bronze events/day (~2 GB raw), hourly pipeline,
Gold still daily grain:

| Line item | Rough monthly |
| --- | --- |
| S3 storage (30 d Bronze + compact Silver/Gold) | $1–3 |
| Lambda GB-seconds (Silver/quality dominate) | $5–20 |
| Athena analysts hitting **Gold only** | $1–5 |
| Athena analysts scanning **Bronze JSON** | $50+ (avoid) |
| CloudWatch logs at DEBUG | can exceed compute |

The inflection is always **scan path**, not object count.

## Athena scan costs (the one to watch)

Workgroup cap: **100 MiB bytes-scanned cutoff** per query
(`bytes_scanned_cutoff_per_query = 104857600` in `infra/terraform/athena.tf`).
Athena list price is **$5 / TB scanned** → 100 MiB ≈ **$0.0005** worst
case per query at the cap. Raise the cutoff only when Gold partitions
grow past that.

Rules of thumb:

1. Query **Gold** (`metric`, `dt`, `events`, `amount_usd`) for KPIs.
2. Query Silver only when debugging late events (`silver_late_event_counts`).
3. Never `SELECT *` Bronze JSON from Athena.
4. Rely on partition projection (`dt`) so Athena does not list-scan the
   prefix ([`partitions.md`](partitions.md)).
5. Named queries already project columns; keep it that way.

Simulated cost for the four named queries against a month of demo Gold
(well under 1 MiB): **effectively $0.00**. Against 100 GB unpartitioned
Bronze: **~$0.50 per full-table query**, which is why the cutoff exists.

## Lambda right-sizing

Terraform defaults (`infra/terraform/lambda.tf`):

| Function | Memory | Timeout | Rationale |
| --- | --- | --- |
| ingest | 256 MB | 60 s | JSON parse + S3/SQS; CPU-light |
| silver | 256 MB | 120 s | Row cleanse; raise memory if Parquet encode grows |
| quality | 256 MB | 120 s | Pandera-style checks; CPU bound → try 512 MB before 1024 |
| gold | 256 MB | 120 s | Daily group-by; stays small at current grain |

Cost model: billable GB-seconds = `(memory_mb / 1024) * duration_s`.
Doubling memory **halves duration** on CPU-bound work and is often
cheaper. Measure `RunDurationMilliseconds` (`docs/metrics.md`) on AWS
before changing sizes.

Stay on zip packages for these handlers. Container images add ECR
storage and slower cold starts that this workload does not need.

## Storage and request hygiene

- Bronze is append-only JSON. Compact or expire it if you keep more than
  a few weeks on real AWS (S3 Intelligent-Tiering or a lifecycle rule —
  not applied by default so `make destroy` stays simple).
- Silver / Gold should stay columnar. The local runner writes
  Parquet-shaped objects; do not "temporarily" dump CSV into Gold.
- Athena results land in `s3://{gold}/athena-results/`. Lifecycle-expire
  them at 7–14 days on a real account.
- DynamoDB stays on-demand. Provisioned capacity is not worth it until
  run metadata is thousands of writes/second.

## Observability cost controls

`FEATURE_EMIT_METRICS` / `emit_metrics` default **off**. The catalog is
low cardinality (`Zone` × `Status`), so CloudWatch custom-metric cost is
small when enabled. Do not add unbounded dimensions (`run_id`, object
key).

Log retention is account-default. On AWS set the Lambda log groups to
7 or 14 days; MiniStack does not bill either way.

## Local vs AWS checklist

| Concern | Local (`ENV=local`) | AWS (`ENV=aws`) |
| --- | --- | --- |
| Money | Docker only | Services above |
| Glue / Athena | disabled | enable + keep the 100 MiB cap |
| Custom metrics | off | on if you want dashboards |
| S3 `force_destroy` | on | off |
| Scan risk | none | Bronze-from-Athena |

## How to sanity-check after an AWS apply

```bash
make env ENV=aws
python -m lakehouse metrics          # EstimatedBytes proxy
python -m lakehouse athena           # workgroup cutoff
# AWS console: Cost Explorer filtered to this account + tags
#   Project=lakehouse, Environment=aws, ManagedBy=terraform
```

If Cost Explorer shows Athena as the top line, someone queried the wrong
zone. If Lambda dominates, inspect duration before raising memory.
