# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-07-05

### Added

- CLI: `scan`, `trim`, `export`, `gui` commands
- Batch freezedetect scan → review CSV
- Lossless trim via ffmpeg concat inpoint/outpoint
- LosslessCut CSV export (`--mode dead|keep`)
- External GUI launchers (LosslessCut, frame-checker)
- DevOps: pre-commit, githooks, CI, SemVer scripts
- Cursor rules, hooks, and agent skills (cucut + caveman suite)

[Unreleased]: https://github.com/optimus/cucut/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/optimus/cucut/releases/tag/v0.1.0
