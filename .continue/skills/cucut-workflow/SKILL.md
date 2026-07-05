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

**Single script** — `scripts/validate.sh` — used by CI, pre-commit, and pre-push hooks.

```bash
bash scripts/setup-hooks.sh
pre-commit install-hooks
```

| Trigger | Command |
|---------|---------|
| `git commit` | `validate.sh` |
| `git push` | `validate.sh --pre-push` |
| GitHub Actions | `validate.sh` |

No separate manual steps — hooks match CI exactly.

### What gets checked

| Section | Checks |
|---------|--------|
| Secrets | `scripts/check-secrets.sh` |
| YAML/TOML | workflows, `pyproject.toml` |
| Python | `ruff check`, `ruff format --check` |
| Tests | `pytest` |
| Version | SemVer in `pyproject.toml` + `__init__.py` |

Service-only pushes skip checks — see `scripts/service-paths.list`.

## Language (required)

- **English only** in code, comments, docstrings, CLI messages, docs, commits
- See `.agents/skills/cucut-language/SKILL.md`

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
- [ ] `git commit` / `git push` pass (hooks = CI via `validate.sh`)
- [ ] CHANGELOG.md updated under [Unreleased]
- [ ] Tests for logic changes
- [ ] bash scripts/bump-version.sh before push to main (app code)
- [ ] No secrets in diff
```
