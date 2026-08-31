# Releases

Package version lives in two places that must stay equal:

- `pyproject.toml` → `[project].version`
- `src/lakehouse/__init__.py` → `__version__`

User-facing notes live in [`CHANGELOG.md`](../CHANGELOG.md) using
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) headings:

```markdown
## [Unreleased]
## [X.Y.Z] - YYYY-MM-DD
```

## Cut a release

1. Move bullets from **Unreleased** into a new `## [X.Y.Z] - date` section.
2. Set both version fields to `X.Y.Z`.
3. Check the plan (hermetic, no tag written):

   ```bash
   python -m lakehouse release
   make release
   ```

4. Commit the version bump + CHANGELOG on `main`.
5. Create the annotated tag from a clean tree:

   ```bash
   make tag VERSION=X.Y.Z
   git push origin main --tags
   ```

`make tag` refuses to run when the plan is dirty (version mismatch, missing
CHANGELOG section). It is a no-op if `vX.Y.Z` already exists.

`python -m lakehouse release --tag` is the same as `make tag` and still
requires `--tag` so CI / unit tests cannot mint tags by accident.

## Current line

`0.1.0` is the working-lakehouse tag (Phases 0–4 plus Phase 5 polish except
optional streaming and the shared-lib extract). `1.0.0` stays in Unreleased
until those P2 items land or are explicitly dropped.
