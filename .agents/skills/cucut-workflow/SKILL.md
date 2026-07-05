---
name: cucut-workflow
description: >-
  Cucut development workflow: git flow, pre-push validation, documentation
  updates, modular code, and DevOps. Use when starting features, fixing bugs,
  opening PRs, or before pushing code.
---

# Cucut Workflow

## Git flow (required)

1. `git checkout main && git pull`
2. `git checkout -b feature/short-name` or `fix/short-name`
3. Make focused changes — one logical change per commit/PR
4. Run validation (below)
5. Open PR against `main`

Never commit directly to `main`.

## Pre-push validation

**Automatic** — `.githooks/pre-push` calls `scripts/pre-push-check.sh` on every push.

One-time setup:

```bash
bash scripts/setup-hooks.sh
pre-commit install-hooks
```

Optional manual run (same checks, no push):

```bash
bash scripts/pre-push-check.sh
```

### What gets checked

| Section | Checks |
|---------|--------|
| Secrets | `scripts/check-secrets.sh` |
| YAML/TOML | workflows, `pyproject.toml` |
| Python | `ruff check`, `ruff format --check` |
| Tests | `pytest` |
| Version | SemVer in `pyproject.toml` + `__init__.py` |

Service-only pushes skip checks — see `scripts/service-paths.list`.

## Documentation (required)

| Change type | Update |
|-------------|--------|
| Behaviour change | `CHANGELOG.md` → `[Unreleased]` |
| CLI / setup | `README.md` |
| Contributor flow | `CONTRIBUTING.md` |

## Modular code

- Pure logic in `segments.py`, `csvio.py` — test without ffmpeg
- Subprocess only in `ffmpeg.py`
- CLI stays thin in `cli.py`

## DevOps

- **Validate locally** before push
- **CI mirrors pre-push** — `.github/workflows/ci.yml`
- **Conventional Commits** — enforced via commit-msg hook

## PR checklist

```
- [ ] Hooks installed (`bash scripts/setup-hooks.sh`)
- [ ] `git push` passes (pre-push hook = full validation)
- [ ] CHANGELOG.md updated under [Unreleased]
- [ ] Tests for logic changes
- [ ] bash scripts/bump-version.sh before push to main (app code)
- [ ] No secrets in diff
```
