# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `scan --mode dji` / `pipeline --mode dji`: mostly-static camera detect (-20dB, scale 160)
  for DJI “camera died” scenes where only part of the frame still moves
- `cucut review <csv>`: local web UI to accept/reject segments before `trim`
  (optional: `pip install 'cucut[web]'`)
  - **Filmstrip-first preview**: sparse seek JPEGs (~every 10s) for fast In/Out marking —
    does not re-encode the whole timeline (HTML5 player swap cannot fix 10-bit HEVC)
  - Optional continuous H.264 scrubbing proxy (GPU NVENC queue, one encode at a time;
    320p / 2 fps) via **Build continuous proxy**
  - Quick cut: mark In/Out (`I`/`O`) as a **delete** window; lossless save as
    `*.cut.MP4` **next to the source** (same folder/disk), with on-screen progress
    (cheap single-copy when deleting head/tail-to-EOF; concat only for true middle cuts;
    Out within ~12 s of EOF, or last filmstrip thumb / **Out = end**, counts as delete-to-end)
  - Review UI: **Open in VLC/mpv** for fine seek on the original HEVC
  - Review UI: **Folder** sidebar tab — browse any directory and list MP4/MOV files

### Fixed

- Close open freezedetect segments at EOF (ffmpeg often omits `freeze_end`)
- Pipeline/scan skip unreadable videos (e.g. incomplete MP4 without moov) instead of aborting
- Checkpoint stage CSV after each file so a mid-run failure keeps partial results

## [0.1.4] - 2026-07-05

### Added

- `cucut pipeline`: multi-pass scan (coarse → medium → fine) with candidate filtering and region windows
- `scan --fast`: hwaccel auto, downscale, and sample FPS for faster batch scans

### Changed

- Default `--min-duration` raised to 5 seconds
- Hardware decode prefers `hwaccel auto` (NVDEC on NVIDIA) over plain CUDA

## [0.1.3] - 2026-07-05

### Changed

- Unified validation: `scripts/validate.sh` — single entry point for CI, pre-commit, and pre-push hooks (identical checks)

## [0.1.2] - 2026-07-05

### Fixed

- CI: limit ruff pre-commit hooks to `src/` and `tests/` (skip vendored skills)

### Changed

- README and docs: English only (removed Russian text)
- Added `cucut-language` skill: mandatory English in all repo content

## [0.1.1] - 2026-07-05

### Fixed

- Git hooks run checks automatically; no manual `pre-push-check.sh` before push
- Added `setup-hooks.sh` and `commit-msg` hook (works with `core.hooksPath`)
- Excluded vendored `.agents`/`.continue` skills from ruff in pre-commit

## [0.1.0] - 2026-07-05

### Added

- CLI: `scan`, `trim`, `export`, `gui` commands
- Batch freezedetect scan → review CSV
- Lossless trim via ffmpeg concat inpoint/outpoint
- LosslessCut CSV export (`--mode dead|keep`)
- External GUI launchers (LosslessCut, frame-checker)
- DevOps: pre-commit, githooks, CI, SemVer scripts
- Cursor rules, hooks, and agent skills (cucut + caveman suite)

[Unreleased]: https://github.com/mystique4u/cucut/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/mystique4u/cucut/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/mystique4u/cucut/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/mystique4u/cucut/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/mystique4u/cucut/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mystique4u/cucut/releases/tag/v0.1.0
