# Partition projection and partition management

Athena does not automatically see Hive folders under Silver/Gold. The usual
fix is `MSCK REPAIR TABLE` or Glue `CreatePartition` after every write.
This project instead uses **partition projection**: Glue table parameters
describe the enum × date grid so Athena expands partitions at query time.

## Layout

| Zone | Prefix | Hive keys | Object key |
| --- | --- | --- | --- |
| Silver | `events/` | `event_type`, `dt` | `events/event_type={type}/dt={YYYY-MM-DD}/{event_id}.json` |
| Gold | `metrics/` | `metric`, `dt` | `metrics/metric={type}/dt={YYYY-MM-DD}/part-000.json` |

`event_type` / `metric` values come from the Silver/Gold contracts:

`page_view`, `add_to_cart`, `purchase`, `refund`.

`dt` is projected as a date from `2024-01-01` through `NOW` with format
`yyyy-MM-dd`.

## Glue table parameters

```
projection.enabled = true
projection.event_type.type = enum
projection.event_type.values = page_view,add_to_cart,purchase,refund
projection.dt.type = date
projection.dt.format = yyyy-MM-dd
projection.dt.range = 2024-01-01,NOW
storage.location.template = s3://{silver}/events/event_type=${event_type}/dt=${dt}
```

Gold is the same with `metric` instead of `event_type` and prefix
`metrics/`. Source of truth: `lakehouse.partitions` and
`infra/terraform/glue.tf`.

Projection does **not** create Glue partition objects. That is the point:
writers keep dropping Hive-style keys; readers do not need a repair step.

## Commands

```bash
make partitions
python -m lakehouse partitions
```

The command prints the projection spec plus a lookback-sized expected
window (`LOOKBACK_DAYS`) and, when S3 is reachable, the Hive keys
actually present under Silver/Gold prefixes.

## When to add a Glue partition anyway

- A new event type is introduced: update the contract enum, the
  `projection.*.values` list (Python + Terraform), and this doc.
- You need Lake Formation / Glue crawler inventory: then register
  partitions explicitly; projection still works for Athena.
- `dt` history older than `2024-01-01`: lower `projection.dt.range`.

Related: [`docs/catalog.md`](catalog.md), [`docs/athena.md`](athena.md).
