# cucut

CLI to find frozen/dead segments in DJI/MP4 videos and lossless-trim them with ffmpeg.

Two-phase workflow: **scan → review → trim**. Built-in local web UI (`cucut review`),
or [LosslessCut](https://github.com/mifi/lossless-cut) / CSV edit. Optional batch scan GUI:
[frame-checker](https://github.com/kuvk/frame-checker).

## Requirements

- Python 3.11+
- ffmpeg / ffprobe on `PATH`

## Install

```bash
cd ~/dev/repos/cucut
pip install -e .
# web review UI (FastAPI):
pip install -e ".[web]"
# or with dev tools:
pip install -e ".[dev,web]"
```

## Quick start

```bash
# 1. Scan a folder of clips
cucut scan ~/Videos/DJI -o segments.csv
# DJI “camera died” / mostly-static:  cucut scan … --mode dji

# 2a. Review in the browser (recommended)
cucut review --workspace ~/Videos/DJI          # open that folder as workspace
cucut review                                  # or set CUCUT_WORKSPACE / default path
# → http://127.0.0.1:8765
# Open workspace → Segments (Scan/Stop) · Folder thumbs · Jobs · cuts as *.cut.MP4
# Artifacts: <workspace>/.cucut/{segments.csv,tmp,proxies}

# 2b. Or edit CSV / LosslessCut
#    action: remove | keep | review
cucut export segments.csv -o losslesscut/ --mode dead
cucut gui --tool losslesscut --csv losslesscut/DJI_001.losslesscut.csv ~/Videos/DJI/DJI_001.mp4

# 3. Lossless trim (originals untouched)
cucut trim segments.csv -o ~/Videos/DJI-trimmed/
```

## Commands

| Command | Description |
|---------|-------------|
| `cucut scan INPUT` | Batch freezedetect → `segments.csv` |
| `cucut review [CSV] [--workspace DIR]` | Local web UI: workspace, scan, review, quick cut |
| `cucut trim CSV` | Cut `action=remove`, concat keep via `-c copy` |
| `cucut export CSV` | LosslessCut CSV (`Start,End,Name`) |
| `cucut gui` | Launch LosslessCut or frame-checker |
| `cucut pipeline INPUT` | Multi-pass coarse → medium → fine scan |

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

### review (web UI)

```bash
pip install -e ".[web]"          # once
cucut review --workspace ~/Videos/DJI
cucut review                     # http://127.0.0.1:8765
cucut review --port 8765 --host 127.0.0.1
```

**Workspace** = the video folder you open in the UI (`Open workspace`), or via
`--workspace` / `CUCUT_WORKSPACE`. Manual **Scan** / **Stop** only (no auto-scan).
Artifacts live under `<workspace>/.cucut/`:

| Path | Contents |
|------|----------|
| `.cucut/segments.csv` | Review CSV (scan output) |
| `.cucut/tmp/` | ffmpeg scratch / cut temps |
| `.cucut/proxies/` | filmstrips, folder thumbs, H.264 proxies |

Sidebar: **Open workspace** → **Segments** (Scan / Rescan / Stop; CSV auto-refreshes) ·
**Folder** (thumbnails + duration/codec) · filmstrip In/Out · lossless `*.cut.MP4` next to
source · **Jobs** (scan/filmstrip/proxy/cut) with **Clear**.

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
scan (freezedetect) → segments.csv → review (web) → trim (-c copy concat)
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
