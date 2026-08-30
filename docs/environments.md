# Multi-environment support

The same Terraform module and Python package target two profiles:

| Profile | `ENV` / `LAKEHOUSE_ENV` | Endpoint | Credentials | Glue / Athena | S3 `force_destroy` |
| --- | --- | --- | --- | --- | --- |
| MiniStack | `local` (default; aliases `ministack`, `dev`) | `http://localhost:4566` | dummy `test` / `test` | off | on |
| Real AWS | `aws` (alias `prod`) | AWS APIs | default credential chain | on | off |

Var-files live in [`infra/terraform/envs/`](../infra/terraform/envs/). The Makefile selects one with `-var-file` and a matching Terraform workspace so local and AWS state stay separate when you use the same working copy.

## Local (default)

```bash
make env                 # JSON profile
make up && make infra    # ENV=local implied
```

This is the documented `make up && make infra && make seed && make pipeline` loop. MiniStack health checks still run.

## Real AWS

1. Copy and edit the AWS var-file. **S3 bucket names are globally unique** — change `bronze_bucket` / `silver_bucket` / `gold_bucket` before the first apply.

   ```bash
   # infra/terraform/envs/aws.tfvars
   bronze_bucket = "yourorg-lakehouse-bronze"
   ```

2. Export real credentials (or use `~/.aws/credentials` / an instance role). Do **not** leave `AWS_ACCESS_KEY_ID=test` in `.env`.

   ```bash
   unset AWS_ENDPOINT_URL
   export AWS_PROFILE=your-profile   # or AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
   export AWS_DEFAULT_REGION=us-east-1
   export LAKEHOUSE_ENV=aws
   ```

3. Apply against the `aws` workspace:

   ```bash
   make env ENV=aws
   make infra ENV=aws
   make seed ENV=aws
   make pipeline ENV=aws
   ```

`make infra ENV=aws` skips `scripts/wait_healthy.sh` and does not inject MiniStack dummy keys.

## How names stay isolated

- Resource names are prefixed (`lakehouse-local-*` vs `lakehouse-aws-*`).
- Terraform workspace = profile name (`local` / `aws`).
- Runtime `LAKEHOUSE_ENV` is printed by `python -m lakehouse env`.
- Glue / Athena stay disabled on MiniStack (`enable_glue=false`) and enabled on AWS.

Inspect the resolved profile:

```bash
python -m lakehouse env
make env ENV=aws
```

## State backends

Local state (`infra/terraform/terraform.tfstate` plus workspaces) is fine for MiniStack. For a shared AWS account, move the backend to S3 + DynamoDB locking before the first shared apply. That change is intentionally out of this file so a laptop `make infra` keeps working with zero extra AWS resources.

## Safety rails on AWS

- `force_destroy = false` so `make destroy ENV=aws` will refuse to wipe non-empty buckets.
- Static MiniStack keys are not sent to the provider (`use_static_credentials = false`).
- Default tags: `Project`, `Environment`, `ManagedBy=terraform`.
