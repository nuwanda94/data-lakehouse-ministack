# CI, pre-commit, and required status checks

This repo uses GitHub Actions (`.github/workflows/ci.yml`) plus
[pre-commit](https://pre-commit.com/) so the same lint/format gates run on
a laptop and on every PR.

## Jobs

| Check name (status context) | What it runs | Required on `main` |
| --- | --- | --- |
| `lint` | ruff check + ruff format + `terraform fmt -check` | yes |
| `pre-commit` | `pre-commit run --all-files` (same hooks as `.pre-commit-config.yaml`) | yes |
| `unit` | `make test` (hermetic; no MiniStack) | yes |
| `security` | hermetic secret scan + Checkov + Trivy secrets | yes |
| `ministack-pipeline` | `make up` → `infra` → `seed` → `pipeline` → `query` → `test-integration` | yes |

The workflow job `name:` values above are the GitHub status-check names.
Protect `main` against those exact strings.

Security details and MiniStack Checkov skips: [`docs/security.md`](security.md).

## Local setup

```bash
pip install -e ".[dev]"          # includes pre-commit
pre-commit install               # git hook on commit
make pre-commit                  # run every hook against the whole tree
make lint                        # ruff only
make security                    # hermetic scan; Checkov/Trivy if installed
make ci                          # full local analogue of GHA (needs Docker + Terraform)
```

`pre-commit install` is optional but recommended. CI still runs the same
hooks even if a contributor skips the local hook.

## Required status checks (branch protection)

GitHub cannot apply branch protection from this repo's application code.
A repo admin should set the following on `main`
(Settings → Branches → Branch protection rule):

1. Require a pull request before merging (1 approval is enough for a solo repo).
2. Require status checks to pass before merging:
   - `lint`
   - `pre-commit`
   - `unit`
   - `security`
   - `ministack-pipeline`
3. Require branches to be up to date before merging.
4. Do **not** allow bypassing the above for administrators in a shared repo
   (optional on a personal showcase repo).

Until those settings are flipped in the GitHub UI, the workflow still runs
on every push and pull request to `main`; it is just not *blocking*.

## Why MiniStack stays a required check

`unit` is hermetic. The medallion path (`seed` → zones → quality → gold)
only proves itself against MiniStack. Keeping `ministack-pipeline` required
means a PR cannot land if Compose, Terraform, or a zone handler broke the
local AWS loop.

## Updating hooks

Bump `rev:` pins in `.pre-commit-config.yaml` with
`pre-commit autoupdate`, then run `make pre-commit` and commit the pin
change. Do not let hooks auto-rewrite PRs from CI (`ci.autofix_prs: false`).
