# Gold quarantine / rejected-metric side path

Post-v1.0 increment: Gold no longer writes contract-invalid aggregates
into `metrics/`. Rejected metrics and unreadable Silver contributions
land under a first-class Gold `quarantine/` prefix so analysts never
query them as KPIs.

## Policy

* Dataset: `gold.quarantine`
* Grain: one rejected metric object
* Key: `quarantine/reason={reason}/metric={event_type}/dt={YYYY-MM-DD}/part-000.json`
* Bucket: Gold (`GOLD_BUCKET`, default `lakehouse-local-gold`)
* Producer: `lakehouse.gold.handler.transform_gold`

Valid rows still go to `metrics/metric={event_type}/dt={day}/part-000.json`
plus the DynamoDB gold-metrics table. Quarantined rows **never** get a
DynamoDB metric item.

## Reasons

`lakehouse.transforms.events.gold_metric_failures` emits stable names:

| Reason | When |
| --- | --- |
| `missing_dt` | `dt` is empty |
| `unknown_event_type` | type is not in the four-value commerce enum |
| `non_positive_events` | `events <= 0` |
| `negative_amount` | `amount_usd < 0` |
| `non_numeric_measures` | `events` / `amount_usd` cannot be coerced |
| `unreadable_silver` | a Silver object failed `CommerceEvent` validation |

Multiple contract failures are joined with `+` in the Hive `reason=`
segment (same pattern as Silver quality quarantine).

## Run

```
make gold
python -m lakehouse gold
```

The Gold handler response includes `quarantine_written` (list of keys)
and `metrics.quarantine_written` (count). Idempotent replays of a
succeeded Gold run do not rewrite either prefix.

## Object shape

```json
{
  "reason": "unreadable_silver",
  "zone": "gold",
  "payload": {
    "source_key": "events/event_type=purchase/dt=2026-01-02/broken.json",
    "payload": {"event_id": "broken"}
  }
}
```

Contract-invalid aggregates keep the attempted metric fields in
`payload` (`dt`, `event_type`, `events`, `amount_usd`).

## Retention

Expired Gold quarantine partitions are planned by
`python -m lakehouse gold-quarantine-retention` (see
[`gold-quarantine-retention.md`](gold-quarantine-retention.md)). Default
TTL is 30 days.

Fragmented quarantine partitions are planned by
`python -m lakehouse gold-quarantine-compact` (see
[`gold-quarantine-compact.md`](gold-quarantine-compact.md)). Default
budget is 2 objects per `reason=/metric=/dt=` prefix.
