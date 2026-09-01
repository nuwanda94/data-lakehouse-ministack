# Shared libraries

Zone Lambdas used to each copy S3 list/get/put JSON and S3-event key
extraction. That logic now lives in one module so a prefix or encoding
change happens once.

| Module | What it owns | Used by |
| --- | --- | --- |
| `lakehouse.storage` | `list_keys`, `load_json`, `put_json`, `keys_from_event`, `load_pairs` | Silver, Gold, quality handlers |
| `lakehouse.pipeline.runs` | `new_run`, `complete_run`, `persist_run`, DynamoDB encode/decode | Bronze, Silver, Gold, quality |
| `lakehouse.pipeline.idempotency` | Deterministic run ids + replay | Bronze, Silver, Gold |
| `lakehouse.ingest.s3_events` | Parse S3 / SQS / EventBridge object refs | Ingest + `storage.keys_from_event` |
| `lakehouse.aws` | boto3 client factory (MiniStack or real AWS) | Every live path |

Handlers stay thin: resolve settings, call storage, run the zone
transform, persist the run, return a JSON result.

```text
event / batch list
        |
        v
lakehouse.storage.keys_from_event + load_pairs
        |
        v
zone transform (cleanse / quality / aggregate)
        |
        v
lakehouse.storage.put_json
        |
        v
pipeline.runs.complete_run + persist_run
```
