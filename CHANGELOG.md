# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/mystique4u/cucut/compare/v0.1.3...HEAD
[0.1.3]: https://github.com/mystique4u/cucut/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/mystique4u/cucut/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/mystique4u/cucut/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mystique4u/cucut/releases/tag/v0.1.0
