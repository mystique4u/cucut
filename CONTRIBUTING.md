# Contributing to cucut

## Setup

```bash
git clone <repo-url> cucut && cd cucut
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
pre-commit install --hook-type commit-msg
git config core.hooksPath .githooks
```

Requires **ffmpeg** and **ffprobe** in `PATH`.

## Branch workflow

1. Branch from `main`: `feature/...` or `fix/...`
2. Make focused changes with tests
3. Update `CHANGELOG.md` under `[Unreleased]`
4. Run `bash scripts/pre-push-check.sh`
5. Open PR to `main`

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(scan): add recursive directory flag
fix(trim): handle empty keep intervals
docs: update LosslessCut export section
chore(release): v0.2.0
```

Commit-msg hook validates format via `conventional-pre-commit`.

## Code style

- **Modular**: one responsibility per module (see `AGENTS.md`)
- **Ruff** for lint + format (`ruff check`, `ruff format`)
- Match existing patterns in surrounding code
- Tests for logic in `segments.py`, `csvio.py`

## Before push

```bash
bash scripts/pre-push-check.sh
```

Same checks run in CI (`.github/workflows/ci.yml`).

## Releasing

```bash
bash scripts/bump-version.sh        # or patch/minor/major
# Finalize CHANGELOG [Unreleased] → [X.Y.Z]
bash scripts/pre-push-check.sh
git commit -m "chore(release): vX.Y.Z"
git tag vX.Y.Z
git push origin main --tags
```

## What not to commit

- `.venv/`, `__pycache__/`, `.pytest_cache/`
- `*.trimmed.mp4`, test output videos
- Secrets, credentials
