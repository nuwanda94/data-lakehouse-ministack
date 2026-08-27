# data-lakehouse-ministack

Local medallion lakehouse (Bronze / Silver / Gold) running against
[MiniStack](https://github.com/ministackorg/ministack) on `localhost:4566`.

## Package layout

Python code lives under `src/lakehouse` so scripts, Lambdas, and tests share
one import path:

```
src/lakehouse/
  config.py        # Settings + load_settings()
  aws.py           # boto3 client factory
  cli.py           # `python -m lakehouse`
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

Environment defaults match `.env.example`. Copy that file to `.env` when you
start using the local stack; dotenv loading is a follow-up chore.

See `TODO.md` for the implementation plan and `PROGRESS.md` for the run log.
