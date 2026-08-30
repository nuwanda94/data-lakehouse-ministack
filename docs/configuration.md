# Centralized configuration

Runtime knobs that are not infrastructure names live in one place:

- [`configs/pipeline.json`](../configs/pipeline.json) — checked-in defaults for lookback, quality thresholds, partition prefixes, and feature flags
- Optional SSM parameter `/lakehouse-local/pipeline` (Terraform `aws_ssm_parameter.pipeline`) — same JSON shape, used when `SSM_ENABLED=true`
- Process environment / `.env` / Terraform outputs — always win

## Precedence (highest first)

1. Existing process environment variables (Makefile, Lambda env, `scripts/tf_env.sh`)
2. SSM parameter JSON, if `SSM_ENABLED` is truthy
3. `configs/pipeline.json` (or `LAKEHOUSE_CONFIG` path)
4. Hard-coded `_DEFAULTS` in `lakehouse.config`

Infrastructure names (`BRONZE_BUCKET`, queue URLs, table names) stay env-driven so MiniStack Terraform outputs remain authoritative. The config file is for *behavior*: feature flags, quality thresholds, partition strategy.

## Keys

| Setting | Env | File path | Default |
| --- | --- | --- | --- |
| Lookback window | `LOOKBACK_DAYS` | `lookback_days` | `2` |
| Quality on-fail | `QUALITY_ON_FAIL` | `quality.on_fail` | `fail` (`quarantine` also valid) |
| Quality max fail ratio | `QUALITY_MAX_FAIL_RATIO` | `quality.max_fail_ratio` | `0.0` |
| Partition strategy | `PARTITION_STRATEGY` | `partitions.strategy` | `hive` |
| Bronze prefix | `BRONZE_PREFIX` | `partitions.bronze_prefix` | `events/` |
| Silver prefix | `SILVER_PREFIX` | `partitions.silver_prefix` | `events/` |
| Gold prefix | `GOLD_PREFIX` | `partitions.gold_prefix` | `metrics/` |
| Feature: Step Functions graph | `FEATURE_SFN` | `features.sfn` | `true` |
| Feature: extra custom metrics | `FEATURE_EMIT_METRICS` | `features.emit_metrics` | `false` |
| Feature: load SSM overlay | `SSM_ENABLED` / `FEATURE_SSM` | `features.ssm` | `false` |
| SSM parameter name | `CONFIG_SSM_PARAMETER` | `ssm.parameter` | `/lakehouse-local/pipeline` |
| Config file path | `LAKEHOUSE_CONFIG` | — | `configs/pipeline.json` |

## Inspect

```bash
python -m lakehouse settings
python -m lakehouse settings --no-dotenv --no-file
```

`make settings` is a thin wrapper.

## Changing a threshold locally

Edit `configs/pipeline.json`, or export:

```bash
export QUALITY_ON_FAIL=quarantine
export QUALITY_MAX_FAIL_RATIO=0.05
export LOOKBACK_DAYS=3
```

On MiniStack / AWS, `make infra` publishes the file contents to SSM so Lambdas can opt in with `SSM_ENABLED=true` without rebuilding the zip.
