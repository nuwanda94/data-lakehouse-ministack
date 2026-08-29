# Bronze dead-letter queue and redrive

Poison or repeatedly failing Bronze S3 events land on a dedicated SQS
dead-letter queue so they do not block the ingest mapping.

## Resources

| Resource | Terraform | Setting |
| --- | --- | --- |
| Source queue | `aws_sqs_queue.bronze_events` | `BRONZE_EVENTS_QUEUE` |
| DLQ | `aws_sqs_queue.bronze_events_dlq` | `BRONZE_EVENTS_DLQ` |
| Redrive policy | `maxReceiveCount` (default 3) | `bronze_events_max_receive_count` |

The ingest Lambda IAM policy can `SendMessage` / `ReceiveMessage` /
`DeleteMessage` on both queues.

## Local path

MiniStack may not always apply SQS redrive. The local drain
(`python -m lakehouse ingest`) therefore **copies a failed message onto
the DLQ** before deleting it from the source queue so operators still
have a reprocessing path.

## Commands

```bash
make dlq                  # peek DLQ bodies
python -m lakehouse dlq --max 10

make redrive              # DLQ → bronze-events
python -m lakehouse redrive --max 10
```

After a redrive, run `make ingest` (or wait for the event-source mapping)
to process the restored messages.

Inspect failed runs with `make runs` — ingest records `status=failed`
when the Bronze object is missing.
