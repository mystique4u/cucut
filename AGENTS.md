# Cucut — Agent Entrypoint

Starting point for AI agents (Cursor, Continue, Claude Code) in this repository.

## What this project is

**Cucut** is a CLI for detecting and trimming frozen/dead segments in DJI/MP4 videos:

1. `scan` — batch `ffmpeg freezedetect` → review CSV
2. review — edit CSV `action` column
3. `trim` — lossless cut (`-c copy` + concat)
4. `export` — LosslessCut CSV; `gui` — open LosslessCut / frame-checker

## Read first

| Resource | Purpose |
|----------|---------|
| [README.md](README.md) | User docs, quick start |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Setup, branch workflow, validation |
| [CHANGELOG.md](CHANGELOG.md) | Version history (Keep a Changelog + SemVer) |
| `.agents/skills/cucut-project/` | Architecture and module layout |
| `.agents/skills/cucut-workflow/` | Git flow, pre-push, docs |
| `.agents/skills/cucut-versioning/` | SemVer on every main push |
| `.agents/skills/cucut-language/` | **English-only** repo content policy |

## Language (mandatory)

**English only** in code, comments, docs, CLI messages, commits, and skills you write.
Read `.agents/skills/cucut-language/SKILL.md`. User chat may be any language; repo files must be English.

## Token efficiency skills

| Skill | When |
|-------|------|
| `caveman` | User wants terse / less tokens |
| `caveman-compress` | Compress .md docs to save context |
| `cavecrew` | Compressed subagent delegation |
| `caveman-commit` | Draft conventional commit messages |
| `caveman-review` | Terse code review |
| `caveman-help` | Skill discovery |

## Project layout

```
src/cucut/
  cli.py          # argparse commands
  scan.py         # batch freezedetect
  csvio.py        # review CSV
  segments.py     # interval math (pure)
  ffmpeg.py       # ffprobe / ffmpeg subprocess
  trim.py         # lossless trim
  export.py       # LosslessCut CSV
  gui.py          # external GUI launchers
tests/            # unit tests
scripts/          # pre-push, bump-version, secret scan
.githooks/        # pre-commit, pre-push
.cursor/          # Cursor rules + hooks
.agents/skills/   # agent skills
.github/workflows/ # CI
```

## Mandatory workflow

### 0. Branch first

```bash
git checkout main && git pull
git checkout -b feature/short-description   # or fix/...
```

Never implement on `main`.

### 1. Modular changes

- Pure logic → `segments.py`, `csvio.py` (unit-testable)
- ffmpeg subprocess → `ffmpeg.py` only
- CLI → `cli.py` only (thin wrapper)

### 2. Update documentation

Add behaviour changes under `CHANGELOG.md` → `[Unreleased]`.

Before push to `main` with app code:

```bash
bash scripts/bump-version.sh
# Move [Unreleased] → [X.Y.Z] - YYYY-MM-DD
git add pyproject.toml src/cucut/__init__.py CHANGELOG.md
```

### 3. Commit and push — hooks run full CI validation

After one-time `bash scripts/setup-hooks.sh`, every hook calls **`scripts/validate.sh`** (same as GitHub Actions):

| Git action | Hook | Script |
|------------|------|--------|
| `git commit` | pre-commit | `scripts/validate.sh` |
| `git commit` | commit-msg | conventional commit format |
| `git push` | pre-push | `scripts/validate.sh --pre-push` |

CI job runs `bash scripts/validate.sh` — identical checks.

Optional manual run: `bash scripts/validate.sh`

## Service paths (no version bump / skip CI checks)

Changes only under paths in `scripts/service-paths.list` (`.cursor/`, `.agents/`, docs, scripts) skip app validation.

## Required checks

- `pre-commit run --all-files`
- `pytest`
- `ruff check src tests`

## Cursor hooks

- `sessionStart` → injects AGENTS context
- `beforeShellExecution` → reminds to run pre-push before `git push`

See `.cursor/hooks.json`.
