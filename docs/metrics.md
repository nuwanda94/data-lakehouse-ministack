# Structured metrics

Phase 4 publishes a small CloudWatch custom-metric catalog so operators can
see **records processed**, **quality failures**, **lag**, and a **cost
proxy** without scraping DynamoDB run rows.

Namespace: `Lakehouse/Medallion`. Dimension `Zone` is always set
(`bronze` / `silver` / `quality` / `gold`). `Status` is attached as a
second dimension.

## Catalog

| Metric | Unit | Meaning |
| --- | --- | --- |
| `RecordsProcessed` | Count | Objects / rows accepted by the zone |
| `QualityFailures` | Count | Rows that failed the Silver quality gate |
| `QualityFailRatio` | None | Failed / scanned on a quality run |
| `LateEvents` | Count | Silver events behind the lookback watermark |
| `PipelineLagSeconds` | Seconds | Finish time minus latest `event_ts` when known |
| `EstimatedBytes` | Bytes | Cost proxy: `records * 2KiB` + Gold objects `* 8KiB` |
| `ObjectsWritten` | Count | S3 objects written by the zone |
| `RunDurationMilliseconds` | Milliseconds | Handler wall clock |

The byte constants are *proxies* — they are not billed bytes. Use them to
compare runs, not to forecast the AWS invoice.

## How metrics are emitted

1. **In-process buffer.** Every `emit_run_metrics(...)` call appends
   `MetricPoint`s. `python -m lakehouse metrics` dumps the catalog plus
   whatever the current process has recorded.
2. **CloudWatch.** When `FEATURE_EMIT_METRICS=true` the same points are
   sent with `PutMetricData`. Failures (MiniStack without CloudWatch) are
   swallowed; the pipeline still succeeds (`backend=buffer`).
3. **DynamoDB run row.** Zone handlers still write the raw counters onto
   `pipeline-runs`. That remains the source of truth for a single run.

## Flags

| Setting | Default | Notes |
| --- | --- | --- |
| `FEATURE_EMIT_METRICS` / `features.emit_metrics` | `false` | Turns on PutMetricData |
| Terraform `emit_metrics` | `false` | Injects the env var onto zone Lambdas |

Keep the flag off against MiniStack. Flip it for real AWS:

```bash
export FEATURE_EMIT_METRICS=true
# or
terraform apply -var emit_metrics=true
```

IAM already allows `cloudwatch:PutMetricData` on the Lambda role.

## Inspect

```bash
python -m lakehouse metrics
make metrics
```
