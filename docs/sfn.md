# Step Functions medallion state machine

Phase 2 control plane. Zone work still lives in the ingest / silver / quality /
gold handlers; this graph only sequences them.

## Graph

```
IngestBronze → TransformSilver → QualityGate → QualityChoice
                                      │
                          passed ─────┴──► AggregateGold → Succeeded
                          failed ────────► QualityFailed
any Task error ──────────────────────────► Failed
```

Each Task uses `arn:aws:states:::lambda:invoke` with Retry (3 attempts, 2s
backoff) and a Catch-all to `Failed`. The Choice inspects
`$.quality.passed` and `$.quality.status`.

## Artifacts

| Path | Role |
| --- | --- |
| `src/lakehouse/orchestration/sfn.py` | ASL builder + local interpreter |
| `infra/terraform/sfn.asl.json.tftpl` | Template Terraform renders with Lambda ARNs |
| `infra/terraform/sfn.tf` | IAM role + `aws_sfn_state_machine.medallion` |

`tests/test_sfn.py` asserts the Python graph and the Terraform template stay
aligned.

## How to run

Local interpreter (same zone order, no SFN service required):

```bash
make sfn                  # after make up / infra / seed
python -m lakehouse sfn
python -m lakehouse sfn-def
```

On MiniStack or real AWS, `make infra` deploys the state machine. Start an
execution with the AWS CLI once the emulator (or account) supports SFN:

```bash
aws stepfunctions start-execution \
  --state-machine-arn "$SFN_STATE_MACHINE_ARN" \
  --input '{"run_id":"demo"}'
```

`make pipeline` remains the v0.1 Python runner (ADR-003). Prefer `make sfn`
when you want the Phase 2 graph.
