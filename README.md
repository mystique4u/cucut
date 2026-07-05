# cucut

CLI to find frozen/dead segments in DJI/MP4 videos and lossless-trim them with ffmpeg.

Two-phase workflow: **scan → review → trim**. For GUI review use [LosslessCut](https://github.com/mifi/lossless-cut); optional batch scan GUI: [frame-checker](https://github.com/kuvk/frame-checker).

## Requirements

- Python 3.11+
- ffmpeg / ffprobe on `PATH`

## Install

```bash
cd ~/dev/repos/cucut
pip install -e .
# or with dev tools:
pip install -e ".[dev]"
```

## Quick start

```bash
# 1. Scan a folder of clips
cucut scan ~/Videos/DJI -o segments.csv

# 2. Review CSV (LibreOffice / VS Code / LosslessCut)
#    action: remove | keep | review
#    high-confidence freeze → remove by default

# 3. LosslessCut CSV for visual review (optional)
cucut export segments.csv -o losslesscut/ --mode dead
cucut gui --tool losslesscut --csv losslesscut/DJI_001.losslesscut.csv ~/Videos/DJI/DJI_001.mp4

# 4. Lossless trim (originals untouched)
cucut trim segments.csv -o ~/Videos/DJI-trimmed/
```

## Commands

| Command | Description |
|---------|-------------|
| `cucut scan INPUT` | Batch freezedetect → `segments.csv` |
| `cucut trim CSV` | Cut `action=remove`, concat keep via `-c copy` |
| `cucut export CSV` | LosslessCut CSV (`Start,End,Name`) |
| `cucut gui` | Launch LosslessCut or frame-checker |

### scan

```bash
cucut scan ~/Videos/DJI -o segments.csv \
  --noise -60 \
  --min-duration 3
```

Default `freezedetect` params: `noise=-60dB`, `min_duration=3s`.

### Review CSV

| path | seg_start | seg_end | duration | dead_sec | confidence | action | reviewed |
|------|-----------|---------|----------|----------|------------|--------|----------|
| DJI_001.mp4 | 98.200 | 142.500 | 600.000 | 44.300 | high | remove | no |

- **duration** — file length (seconds)
- **dead_sec** — freeze interval length
- **action**: `remove` (cut out), `keep` (keep freeze), `review` (decide manually)

### trim

```bash
cucut trim segments.csv -o ./trimmed/ --dry-run   # plan only, no ffmpeg
cucut trim segments.csv -o ./trimmed/
```

Dead intervals are inverted to keep; stitched via concat demuxer (`inpoint`/`outpoint`), like [speedrun](https://github.com/benjaminjackson/speedrun).

**Limitation:** with `-c copy`, cut accuracy is ± keyframe (0.5–2 s). Originals are not modified; output: `*.trimmed.mp4`.

### export (LosslessCut)

```bash
cucut export segments.csv -o losslesscut/ --mode dead   # freezes for review
cucut export segments.csv -o losslesscut/ --mode keep    # keep segments for export
```

Format: header `Start,End,Name`, times in seconds — compatible with LosslessCut import.

### gui

```bash
cucut gui --tool losslesscut DJI_001.mp4
cucut gui --tool frame-checker
```

## Architecture

```text
scan (freezedetect) → segments.csv → [review] → trim (-c copy concat)
                              ↓
                    export → LosslessCut CSV → gui
```

Inspired by [speedrun](https://github.com/benjaminjackson/speedrun) (invert + concat), [deadframe](https://github.com/agatan/deadframe) (detect, `-print`), [frame-checker](https://github.com/kuvk/frame-checker) (batch GUI scan), [LosslessCut](https://github.com/mifi/lossless-cut) (review + lossless export).

## Tests

```bash
pytest
# git hooks + CI run: bash scripts/validate.sh
```

## DevOps and agents

- [AGENTS.md](AGENTS.md) — entrypoint for Cursor/Continue
- [CONTRIBUTING.md](CONTRIBUTING.md) — workflow, conventional commits
- `bash scripts/setup-hooks.sh` — enable pre-commit / pre-push hooks
- Skills: `.agents/skills/` (cucut-*, caveman for token savings)
- CI: `.github/workflows/ci.yml`

## License

MIT
