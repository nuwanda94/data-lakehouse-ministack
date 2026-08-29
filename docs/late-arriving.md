# Late-arriving data

Gold metrics are partitioned by **event time** (`event_ts` date), not
ingest time. An event that shows up two days late still belongs to the
original day and must reopen that Gold object.

## Lookback window

`LOOKBACK_DAYS` (default `2`) is the inclusive calendar window behind
`as_of` (default: now UTC):

```
[as_of.date() - LOOKBACK_DAYS, as_of.date()]
```

Silver uses the same window as the late watermark in
`cleanse_to_silver`. Events older than the cutoff are still written to
Silver (they are valid commerce events) but tagged `"_late": true` so a
reprocess run can see them.

Override per invocation:

```bash
LOOKBACK_DAYS=7 make reprocess
python -m lakehouse reprocess --lookback-days 7 --as-of 2026-01-10
```

## Reprocess path

`python -m lakehouse reprocess` / `make reprocess`:

1. List Silver objects under `events/`.
2. Keep keys whose Hive `dt=YYYY-MM-DD` partition is inside the window.
3. Load those events and `aggregate_gold` over the **full** partition
   (on-time + late rows). Partial overwrites would under-count the day.
4. Put the Gold object and DynamoDB `gold-metrics` row for each
   `(event_type, dt)` touched.
5. Record a `zone=gold` / `step=reprocess` pipeline run.

Idempotency still fingerprints the window + Silver keys, so a second
reprocess of the same content keeps a stable `run_id`.

## Why not fold this into the Gold Lambda?

The event-driven Gold handler aggregates only the Silver objects in the
current batch. That is correct for a first write of those keys, but a
late row for `dt=2026-01-08` must be merged with every other Silver
event already in that partition. Reprocess is the merge.
