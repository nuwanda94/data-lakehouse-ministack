# data-lakehouse-ministack

Local medallion lakehouse (Bronze / Silver / Gold) running against
[MiniStack](https://github.com/ministackorg/ministack) on `localhost:4566`.

## Package layout

Python code lives under `src/lakehouse` so scripts, Lambdas, and tests share
one import path:

```
src/lakehouse/
  config.py        # Settings + load_settings() / load_dotenv()
  aws.py           # boto3 client factory
  cli.py           # `python -m lakehouse`
  ops/outputs.py   # Terraform output → env mapping
  seed/            # bronze sample data
  pipeline/        # orchestration
  transforms/      # zone transforms
  quality/         # quality gates
tests/
```

Install (editable) and verify imports:

```bash
python -m pip install -e ".[dev]"
python -c "from lakehouse import load_settings; print(load_settings().bronze_bucket)"
python -m lakehouse --version
pytest
```

Copy `.env.example` to `.env` to override defaults. `load_settings()` reads
that file automatically and **does not** override variables already present
in the process environment (Makefile / Terraform output injection wins).

See `TODO.md` for the implementation plan and `PROGRESS.md` for the run log.

## Local loop

Requires Docker and Terraform.

```bash
make install
make up          # MiniStack on :4566 + health check
make infra       # S3 buckets + DynamoDB tables
make outputs     # KEY=value from Terraform (or state / defaults)
make seed        # synthetic events → bronze
make pipeline    # bronze → silver → gold
make query
make test
```

`make seed` / `make pipeline` / `make query` eval `scripts/get_outputs.sh` so
bucket and table names stay in sync with Terraform. Equivalent Python:

```bash
eval "$(python -m lakehouse outputs --export)"
python -m lakehouse outputs --write-env .env.generated
```
