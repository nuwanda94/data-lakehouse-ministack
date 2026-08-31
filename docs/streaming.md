# Optional streaming path (Kinesis / Firehose)

The default producer is batch: `make seed` writes one JSON object per
event into Bronze. Phase 5 adds an optional streaming-shaped producer
that encodes the same commerce events as Kinesis records, buffers them
as a Firehose batch, and lands them on the same Bronze prefix so the
existing S3 → SQS → Lambda ingest path stays unchanged.

```text
generate_events
    → Kinesis PutRecords   (partition key = user_id)
    → Firehose PutRecordBatch / delivery stream
    → s3://bronze/events/dt=YYYY-MM-DD/<event_id>.json
    → existing ingest / silver / quality / gold
```

This path is **optional**. MiniStack CI and `make infra` leave it off
(`enable_streaming = false`) so a workstation without Kinesis APIs still
applies cleanly.

## Offline (always works)

```bash
python -m lakehouse stream --mode offline --count 20
# or: --sink kinesis | firehose | both
```

The offline backend never talks to AWS. It:

1. Generates deterministic events (`seed=42`).
2. Encodes Kinesis (`PartitionKey` + base64 `Data`) and Firehose records.
3. Simulates Firehose S3 delivery via `bronze_key()`.
4. Round-trips the payload so tests can assert `event_id` survives encoding.

## Live (MiniStack / AWS)

```bash
make stream
# or: python -m lakehouse stream --mode live --count 20
```

Live mode:

1. `PutRecords` against `KINESIS_STREAM` (default `lakehouse-local-events`).
2. `PutRecordBatch` against `FIREHOSE_STREAM` (default `lakehouse-local-events-firehose`).
3. Writes the same events to Bronze so Silver can run even if MiniStack
   Firehose delivery is delayed or unimplemented.

Kinesis/Firehose errors are recorded in `live_errors` and do **not** fail
the command if Bronze writes succeed. `--mode auto` falls back to offline
when the AWS client cannot be reached at all.

## Terraform

`infra/terraform/streaming.tf` is gated:

```hcl
enable_streaming = true   # local.tfvars / aws.tfvars default false
```

When enabled it creates:

- `aws_kinesis_stream.events`
- IAM role for Firehose
- `aws_kinesis_firehose_delivery_stream.events` with an extended S3
  destination on the Bronze bucket (`events/dt=!{timestamp:yyyy-MM-dd}/`)

Turn it on only when you want to exercise the streaming APIs. The
Python producer does not require the Terraform resources for the
offline path.

## Config

| Setting | Env | Default |
| --- | --- | --- |
| Feature flag | `FEATURE_STREAMING` / `features.streaming` | `false` |
| Kinesis stream name | `KINESIS_STREAM` | `lakehouse-local-events` |
| Firehose delivery name | `FIREHOSE_STREAM` | `lakehouse-local-events-firehose` |

See also [`docs/configuration.md`](configuration.md).
