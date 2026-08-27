# data-lakehouse-ministack

Local medallion (bronze / silver / gold) lakehouse that runs against
[MiniStack](https://github.com/ministackorg/ministack) on `localhost:4566`.

## Package layout

```
src/lakehouse/
  config.py          Settings from env / .env
  aws.py             boto3 session + client factory
  models.py          CommerceEvent, PipelineRun, QualityResult
  cli.py             `lakehouse version|config`
  seed/              Synthetic event generation
  pipeline/          Zone key helpers + quality checks
tests/               Import and layout contract tests
```

Install (editable):

```bash
python -m pip install -e ".[dev]"
python -m lakehouse version
pytest
```

See `TODO.md` and `PROGRESS.md` for the implementation plan.
