# Analytical data model

Analyst-facing view of the lakehouse: grain, facts, dimensions, metrics,
and the questions Gold is designed to answer. Field-level types live in
[`data-dictionary.md`](data-dictionary.md) and
[`configs/contracts/`](../configs/contracts/). Catalog / Athena wiring is
in [`catalog.md`](catalog.md) and [`athena.md`](athena.md).

## Purpose

The pipeline turns raw commerce events into a **daily event-type fact**
that an analyst (or Athena named query) can read without joining Bronze.

| Layer | Role for analytics | Use it when |
| --- | --- | --- |
| Bronze `commerce_event_raw` | Immutable landing; schema is best-effort | Debugging producers, replaying a day |
| Silver `commerce_event_conformed` | Event-level fact + `_late` flag | Funnels, user/SKU slices, late-vs-on-time |
| Quarantine | Rejected Bronze rows | Data-quality RCA — **not** for KPIs |
| Gold `daily_event_metrics` | Daily grain by `event_type` | Dashboards, revenue proxy, day-over-day |

Do **not** mix quarantine objects into KPI queries. Gold only reads
`silver/events/…`.

## Business process

One row in Bronze/Silver is a **commerce event**: a shopper viewed a
page, added a SKU to cart, purchased, or refunded.

Allowed `event_type` values (contract enum):

- `page_view`
- `add_to_cart`
- `purchase`
- `refund`

Seed SKUs are `SKU-100` … `SKU-400`. Seed markets are `US`, `DE`, `IN`,
`BR`, `JP`. Those lists are demo fixtures, not a product dimension table.

## Grain

| Dataset | Grain | Unique key |
| --- | --- | --- |
| Silver events | 1 event | `event_id` (also S3 basename) |
| Gold S3 + DynamoDB | 1 (`event_type`, calendar day) | Hive `metric` + `dt`; DDB `metric_day` = `{event_type}#{dt}` |

`dt` is the **event occurrence date** taken from `event_ts`, not the
pipeline run date. Late events keep their original `dt` and set
`_late = true` on Silver so Gold can reopen that partition
(`make reprocess`; see [`late-arriving.md`](late-arriving.md)).

## Logical star (v0.1)

There is no separate dimension warehouse yet. Degenerate dimensions sit
on the event fact.

```
                    ┌─────────────────────────┐
                    │  Gold daily_event_metrics │
                    │  grain: event_type × dt   │
                    │  measures: events,        │
                    │            amount_usd     │
                    └─────────────────────────┤
                                 │ SUM / COUNT
                    ┌─────────────────────────┬
                    │ Silver commerce_event     │
                    │ grain: event_id           │
                    │ dims: event_type, dt,     │
                    │       user_id, sku,       │
                    │       country, _late      │
                    │ measures: quantity,       │
                    │           amount_usd      │
                    └──────────────────────────┘
```

A future dbt layer (Phase 3 P2) should add:

- `dim_date` from projected `dt`
- `dim_event_type` from the contract enum
- `dim_sku` / `dim_country` only after those become first-class contracts

## Facts and measures

### Silver event fact (`commerce_event_conformed`)

Additive measures on the event:

| Measure | Additivity | Definition |
| --- | --- | --- |
| `quantity` | additive across events | Units on the event; Silver requires `> 0` |
| `amount_usd` | additive across events | Gross USD on the event; Silver requires `>= 0` |

`_late` is a **status flag**, not a measure. Count it; do not sum it
into revenue.

### Gold daily fact (`daily_event_metrics`)

Produced by `lakehouse.transforms.events.aggregate_gold`:

| Measure | Source | Definition |
| --- | --- | --- |
| `events` | `COUNT(*)` of Silver events in the (`event_type`, `dt`) bucket | Integer |
| `amount_usd` | `SUM(amount_usd)` rounded to 2 decimal places | Number |

Gold does **not** currently persist `SUM(quantity)`, distinct users, or
AOV. Derive those from Silver until a contract change adds them.

Partition column `metric` on Gold S3 **is** `event_type`. Athena / Glue
expose it as `metric` so projection enums stay aligned with
[`partitions.md`](partitions.md).

## Metric definitions (business)

Use these names in dashboards so Gold and Silver queries stay consistent.

| KPI | Preferred source | Formula | Caveats |
| --- | --- | --- | --- |
| Event volume | Gold `events` | `SUM(events)` | Includes late events after reprocess |
| Gross merchandise (proxy) | Gold `amount_usd` where `metric = 'purchase'` | `SUM(amount_usd)` | Seed amounts are synthetic; refunds are a separate series |
| Refund amount | Gold `amount_usd` where `metric = 'refund'` | `SUM(amount_usd)` | Not netted out of purchase Gold rows |
| Net revenue (approx.) | Gold purchase − Gold refund | two queries, same `dt` range | No tax/discount model |
| Funnel counts | Silver or Gold `events` by type | page_view → add_to_cart → purchase | Not sessionized; no user-journey window |
| Late-event rate | Silver `_late` | `late / (late + on_time)` | Named query `silver_late_event_counts` |
| Average order value | Silver purchases | `SUM(amount_usd) / COUNT(*)` | Not on Gold yet |
| Units sold | Silver purchases | `SUM(quantity)` | Not on Gold yet |

Named Athena queries that already encode the first four patterns:

- `gold_daily_totals`
- `gold_purchase_revenue`
- `gold_last_7_days`
- `silver_late_event_counts`

SQL source of truth: `lakehouse.athena.named_queries()`.

## Dimensions and filters

| Attribute | Lives on | Filter guidance |
| --- | --- | --- |
| `dt` | Silver + Gold | Always constrain it; projection is date `2024-01-01` → `NOW` |
| `event_type` / Gold `metric` | both | Enum of four values — never `SELECT *` without it if you care about one KPI |
| `user_id` | Silver only | No user dim; cardinality is seed-sized |
| `sku` | Silver only | Four seed SKUs |
| `country` | Silver only | Default `US` when Bronze omitted it |
| `_late` | Silver only | Use for freshness / SLA, not GMV |

## Relationships

- Bronze `event_id` = Silver `event_id` = object basename.
- Gold has **no** `event_id`. Join Gold → Silver on
  `gold.metric = silver.event_type AND gold.dt = silver.dt`.
- DynamoDB `lakehouse-local-gold-metrics` is a **serving copy** of Gold
  S3 (`GetItem` on `metric_day`). Prefer Athena for scans; prefer DDB
  for point lookups (`make query`).
- Pipeline-run items are operational, not analytical.

## Example questions

1. **What was purchase GMV yesterday?**
   Gold: `metric = 'purchase' AND dt = DATE '…'` → `amount_usd`.
2. **Did late events move last Tuesday’s refunds?**
   Silver: `_late = true AND event_type = 'refund' AND dt = …` vs Gold
   after `make reprocess`.
3. **Which SKU drove add-to-cart today?**
   Silver only: `GROUP BY sku` — Gold has no SKU.
4. **Is the quality gate hiding volume?**
   Compare Bronze object counts to Silver `events/` vs `quarantine/`.
   Quarantine reasons are listed in `configs/contracts/silver.json`.

## Freshness, late data, and idempotency

- Gold is rebuilt from the Silver keys the Gold handler sees. A full
  local run (`make pipeline`) aggregates the listed prefix.
- Late arrivals do not change `dt`. Reprocess the affected date so the
  Gold object and DynamoDB item are rewritten
  ([`runbook.md`](runbook.md)).
- Idempotent Gold writes use content-aware keys
  ([`idempotency.md`](idempotency.md)); retries must not double-count
  if the handler short-circuits on a prior success.

## What this model is not

- Not a conformed dimensional warehouse (no SCD dimensions).
- Not session or customer 360 (no `session_id`, no identity graph).
- Not audited financials (`amount_usd` is a demo measure).
- Not Parquet-on-S3 yet; Hive keys are Parquet-shaped so Glue/Athena
  can project partitions before the format swap.

## Change control

1. Business meaning changes → update this file **and** the zone
   contract.
2. New Gold measures → `configs/contracts/gold.json`,
   `aggregate_gold`, Glue columns, Athena named queries, tests.
3. Breaking grain changes → ADR under `docs/adr/`.
