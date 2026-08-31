# Contributing

Thanks for looking at the lakehouse. This repo is a local-first, production-shaped
medallion stack. Changes should stay small, typed, and testable offline whenever
possible.

## Ground rules

1. One focused change per PR. Do not finish an entire phase in one commit.
2. Conventional commits: `feat:`, `chore:`, `docs:`, `test:`, `fix:`, `ci:`,
   `refactor:`.
3. Every PR should reference a `TODO.md` line (or a GitHub issue with the same
   title).
4. Do not add cloud-only code paths that break the MiniStack loop.
5. Do not commit secrets, real AWS keys, or MiniStack volume dumps.

## Local setup

```bash
python -m pip install -e ".[dev]"
cp .env.example .env          # optional; dummy MiniStack creds
pre-commit install            # same hooks CI runs
make test                     # hermetic; no Docker
```

Full local AWS loop (needs Docker + Terraform):

```bash
make up && make infra
make demo
make test-integration
```

See the README for every Make target and [`docs/ci.md`](docs/ci.md) for how CI
maps to those targets.

## How we pick work

Live checklist: [`TODO.md`](TODO.md). Run log: [`PROGRESS.md`](PROGRESS.md).

Prefer, in order:

1. Incomplete P0 `chore` / `feat`
2. Incomplete P0 `docs` / `test` / `ci`
3. Incomplete P1

Keep `TODO.md` and `PROGRESS.md` in the same commit as the implementation.

## Branch and PR

```bash
git checkout -b feat/short-slug
# …edit…
make lint
make test
git commit -m "feat: short conventional title"
```

PR title must match the conventional commit. Body should cover:

- What changed and why
- How you tested it (`make test`, `make demo --mode offline`, MiniStack loop)
- Follow-up / leftover risk

Required CI jobs on `main` (see [`docs/ci.md`](docs/ci.md)):

- `lint`
- `pre-commit`
- `unit`
- `ministack-pipeline`

Run `ruff check` and `ruff format` (or `make lint` / `make pre-commit`) on
changed files **before** push. Prefer a clean first commit over “land then fix
lint.”

## Code conventions

- Package lives under `src/lakehouse`. Public CLI is `python -m lakehouse`.
- Settings come from `load_settings()` — process env wins over `.env` wins over
  documented defaults. Do not hard-code bucket names in handlers.
- Zone contracts live in `configs/contracts/`. If you add or rename a field,
  update the contract, the data dictionary, and the quality gate together.
- Unit tests must stay hermetic. Mark MiniStack-only tests with
  `@pytest.mark.integration`.
- Terraform stays in `infra/terraform`. Format with `terraform fmt`. Do not
  check in `.terraform/` or local state.
- Docs for behaviour go under `docs/` (runbook, ADRs, contracts). Keep the
  README as the showcase entry point, not a dump of every knob.

## CODEOWNERS

Review routing lives in [`.github/CODEOWNERS`](.github/CODEOWNERS). The default
owner is `@nuwanda94`. Tighten paths there when a second maintainer owns a
zone (Terraform, quality, dbt, CI).

CODEOWNERS only requests reviews; it does not replace the required status
checks.

## Security

Do not put real credentials in `.env`, fixtures, or screenshots. Use the dummy
MiniStack values from `.env.example`. If you add scanners (Checkov, Trivy,
detect-secrets), wire them through `make` and CI rather than a one-off script.

## License

By contributing you agree the change is licensed under the MIT license in
[`LICENSE`](LICENSE).
