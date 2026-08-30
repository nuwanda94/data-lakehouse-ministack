# Failure injection

Hermetic tests in `tests/test_failure_injection.py` pin how the medallion
path behaves when a zone Lambda dies, an SQS body is garbage, or a producer
ships a drifted schema.

| Fault | Expected behaviour |
| --- | --- |
| Zone Lambda raises | Local SFN interpreter Catch → `Failed`. Downstream zones are not called. |
| Zone handler returns `status=failed` | Same terminal; later states skipped. |
| Quality gate `passed=false` | `QualityFailed`; Gold is not invoked. |
| Poison SQS body (not JSON / no S3 Records) | `extract_object_refs` drops the message. Ingest does not crash. |
| Missing Bronze object | Ingest records `status=failed` + `missing`. |
| Unknown `event_type`, bad measures, invalid timestamp | `parse_bronze_record` raises a stable reason; Silver quarantines the row. |
| Extra unknown columns | Ignored if required fields still validate. |
| Contract drift past the quality gate | Gate fails the run so Gold never sees the batch. |

These tests do not start MiniStack. Live DLQ redrive is covered separately
in `docs/dlq.md` and `tests/test_dlq.py`.
