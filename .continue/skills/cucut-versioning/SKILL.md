---
name: cucut-versioning
description: >-
  Semantic versioning for cucut: bump pyproject.toml, sync __version__,
  CHANGELOG, pre-push version gate, and git tags. Use when releasing, pushing
  to main, bumping version, or updating CHANGELOG.
---

# Cucut Versioning

## Policy

[Semantic Versioning](https://semver.org/) + [Keep a Changelog](https://keepachangelog.com/).

**Every push to `main` with application code must ship a new version.**

Service/meta-only pushes are exempt — paths in `scripts/service-paths.list`.

## Version source of truth

| File | Field |
|------|-------|
| `pyproject.toml` | `version = "X.Y.Z"` |
| `src/cucut/__init__.py` | `__version__ = "X.Y.Z"` |
| `CHANGELOG.md` | `[X.Y.Z] - YYYY-MM-DD` sections |
| Git tag | `vX.Y.Z` |

## Bump workflow

```bash
bash scripts/bump-version.sh          # auto-detect from commits
bash scripts/bump-version.sh patch    # explicit
bash scripts/bump-version.sh minor
bash scripts/bump-version.sh major
```

Auto-detect from conventional commits since last `v*` tag:

| Commit prefix | Bump |
|---------------|------|
| `BREAKING CHANGE` or `type!:` | major |
| `feat:` | minor |
| `fix:`, `chore:`, etc. | patch |

Then move `CHANGELOG.md` `[Unreleased]` → `[X.Y.Z] - date`.

```bash
bash scripts/pre-push-check.sh
git add pyproject.toml src/cucut/__init__.py CHANGELOG.md
git commit -m "chore(release): vX.Y.Z"
git tag vX.Y.Z
git push origin main --tags
```

## Pre-push gate

`.githooks/pre-push` runs `scripts/check-version.sh --pre-push`:

1. Validates semver in `pyproject.toml`
2. Ensures `__version__` matches
3. Checks `CHANGELOG.md` has `[Unreleased]`
4. On push to main (app code): requires version > latest `v*` tag

## Checklist

```
- [ ] bash scripts/bump-version.sh [patch|minor|major]
- [ ] CHANGELOG [Unreleased] → [X.Y.Z] with date
- [ ] bash scripts/check-version.sh passes
- [ ] bash scripts/pre-push-check.sh passes
```
