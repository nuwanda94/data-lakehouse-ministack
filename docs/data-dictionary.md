# Data dictionary — medallion zones

This document is the field-level companion to
[`configs/contracts/`](../configs/contracts/). Grain, KPIs, and how to
query Gold vs Silver are in
[`analytical-model.md`](analytical-model.md). Field names, types, and
partition keys must match those JSON files and `lakehouse.models`.

## Zones at a glance

| Zone | Bucket (local default) | Prefix | Grain | Written by |
| --- | --- | --- | --- | --- |
| Bronze | `lakehouse-local-bronze` | `events/dt={date}/{event_id}.json` | 1 event / object | `make seed` / `lakehouse.ops.seed` |
| Silver | `lakehouse-local-silver` | `events/event_type={type}/dt={date}/{event_id}.json` | 1 valid event / object | Silver Lambda |
| Quarantine | same as Silver | `quarantine/reason={reason}/{event_id}.json` | 1 rejected row | Silver + quality gate |
| Quality report | same as Silver | `quality/dt={date}/run_id={run_id}.json` | 1 report / run | Quality Lambda |
| Gold | `lakehouse-local-gold` | `metrics/metric={event_type}/dt={date}/part-000.json` | 1 (type, day) | Gold Lambda |
| Gold metrics | DynamoDB `lakehouse-local-gold-metrics` | PK `metric_day` = `{event_type}#{dt}` | same as Gold object | Gold Lambda |
| Pipeline runs | DynamoDB `lakehouse-local-pipeline-runs` | PK `run_id` | 1 item / zone step | every handler |

v0.1 stores **JSON** (Parquet-shaped Hive keys). Phase 3 swaps the Gold/Silver
payloads for Parquet + Glue types without changing field names.

## Commerce event (Bronze + Silver)

Canonical model: `lakehouse.models.CommerceEvent`.

| Field | Type | Required | Allowed values / constraints | Meaning |
| --- | --- | --- | --- | --- |
| `event_id` | string | yes | non-empty; seed = `evt-{seed}-{seq}` | Primary event key; also the S3 object basename |
| `event_ts` | datetime (ISO-8601) | yes | timezone-aware preferred | Occurrence time; drives `dt=` partitions |
| `event_type` | string | yes | `page_view`, `add_to_cart`, `purchase`, `refund` | Business event class |
| `user_id` | string | yes | non-empty | Synthetic shopper |
| `sku` | string | yes | non-empty; seed SKUs `SKU-100`…`SKU-400` | Product |
| `quantity` | integer | yes | Bronze may land any int; Silver requires `> 0` | Units |
| `amount_usd` | number | yes | `>= 0` | Gross amount in USD |
| `country` | string | no (default `US`) | seed: `US`, `DE`, `IN`, `BR`, `JP` | Market |
| `_late` | boolean | Silver only | — | `true` when `event_ts` is older than watermark − 2 days |

### Bronze vs Silver

- Bronze is **append-only landing**. Seed writes valid events; a future
  producer may write junk. Ingest Lambda only HEADs/GETs objects under
  `events/` and records a pipeline run.
- Silver calls `parse_bronze_record` / `cleanse_to_silver`. Failures become
  quarantine objects with a stable `reason` string:
  `empty_record`, `missing_event_id`, `unknown_event_type`,
  `non_numeric_measures`, `non_positive_quantity`, `negative_amount`,
  `schema_invalid`.
- Late-but-valid events are written to Silver `events/` with `"_late": true`
  rather than dropped. Gold includes them in the date partition of
  `event_ts`. Re-opening those partitions is a Phase 2 item.

## Gold daily metrics

Produced by `aggregate_gold`. Empty Silver input yields no Gold objects.

| Field | Type | Meaning |
| --- | --- | --- |
| `dt` | date `YYYY-MM-DD` | Event date |
| `event_type` | string | Same enum as Silver |
| `events` | integer | Count of Silver rows in the bucket |
| `amount_usd` | number | Sum of `amount_usd`, rounded to 2 dp |

DynamoDB mirror (`GOLD_METRICS_TABLE`):

| Attribute | Type | Notes |
| --- | --- | --- |
| `metric_day` | S (PK) | `{event_type}#{dt}` |
| `event_type` | S | |
| `dt` | S | |
| `events` | N | |
| `amount_usd` | N | |

## Quality gate

Default policy: `on_fail=fail`, `max_fail_ratio=0.0` (any bad row fails the
run with status `quality_failed`). `on_fail=quarantine` writes failing rows
under `quarantine/` and lets the run succeed.

| Check name | Passes when |
| --- | --- |
| `event_id_present` | `event_id` is a non-empty string |
| `known_event_type` | type is in the four-value enum |
| `required_dimensions` | `user_id` and `sku` are non-empty |
| `quantity_and_amount_sane` | `quantity > 0` and `amount_usd >= 0` |
| `schema_valid` | payload validates as `CommerceEvent` |

Report object fields: `run_id`, `passed`, `action`, `rows_scanned`,
`rows_failed`, `fail_ratio`, `checks` (list of `QualityResult`).

## Pipeline run metadata

| Field | Type | Meaning |
| --- | --- | --- |
| `run_id` | string | Shared across steps when `LAKEHOUSE_RUN_ID` or `event.run_id` is set |
| `status` | string | `pending` / `running` / `succeeded` / `failed` / `quality_failed` |
| `started_at` / `finished_at` | ISO datetime | |
| `zone` | string | `bronze` / `silver` / `gold` |
| `step` | string | `ingest` / `silver` / `quality` / `gold` / `pipeline` |
| `parent_run_id` | string | Optional correlation to a parent pipeline run |
| `error` | string | Last error message |
| `objects` | JSON list | S3 keys the step touched |
| `quality` | JSON list | `QualityResult` rows |
| `metrics` | JSON map | Step-specific counters (also flattened as DynamoDB attributes) |

## How to change a contract

1. Edit the JSON file under `configs/contracts/`.
2. Update `CommerceEvent` / transforms / handlers to match.
3. Extend `tests/test_contracts.py` if a new required field is added.
4. Note the change in `PROGRESS.md` and, for breaking changes, an ADR.
5. If grain or KPI meaning changed, update [`analytical-model.md`](analytical-model.md).
