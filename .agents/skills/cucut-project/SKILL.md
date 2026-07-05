---
name: cucut-project
description: >-
  Cucut project structure, scan/review/trim pipeline, module layout, and ffmpeg
  integration. Use when exploring the codebase, adding features, or understanding
  how scan, trim, and export relate.
---

# Cucut Project

## Overview

**Cucut** is a CLI tool for DJI/MP4 videos with "dead" (frozen) segments:

1. **scan** — batch `ffmpeg freezedetect` → review CSV
2. **review** — edit `action` column (`remove` / `keep` / `review`)
3. **trim** — invert dead→keep, lossless concat (`-c copy`)
4. **export** — LosslessCut CSV for GUI review

Inspired by [speedrun](https://github.com/benjaminjackson/speedrun), [deadframe](https://github.com/agatan/deadframe), [frame-checker](https://github.com/kuvk/frame-checker), [LosslessCut](https://github.com/mifi/lossless-cut).

## Module layout (strict separation)

| Module | Responsibility |
|--------|----------------|
| `src/cucut/cli.py` | argparse subcommands only |
| `src/cucut/scan.py` | batch directory scan |
| `src/cucut/csvio.py` | review CSV schema + I/O |
| `src/cucut/segments.py` | interval merge/invert (pure) |
| `src/cucut/ffmpeg.py` | ffprobe, freezedetect, concat |
| `src/cucut/trim.py` | trim orchestration from CSV |
| `src/cucut/export.py` | LosslessCut CSV export |
| `src/cucut/gui.py` | launch LosslessCut / frame-checker |

## Review CSV schema

```
path, seg_start, seg_end, duration, dead_sec, confidence, action, reviewed
```

- `duration` = file length (seconds)
- `dead_sec` = freeze interval length
- `action`: `remove` | `keep` | `review`

## Default detect params

- `noise=-60dB`, `min_duration=3s`

## Key directories

```
src/cucut/           # application code
tests/               # unit tests (segments, csvio)
scripts/             # pre-push, bump-version, secret scan
.githooks/           # pre-commit, pre-push
.cursor/             # Cursor rules + hooks
.agents/skills/      # agent skills (cucut-*, caveman-*)
.github/workflows/   # CI
```

## Entrypoint for agents

Read [AGENTS.md](../../AGENTS.md) at repo root before making changes.
All repo content must be **English only** — see `cucut-language` skill.
