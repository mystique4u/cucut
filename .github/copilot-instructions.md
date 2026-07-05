# Agent instructions for cucut

Read [AGENTS.md](../AGENTS.md) first.

## Safety

- Never modify source video files in place; output to separate dir or `*.trimmed.mp4`
- Never commit secrets or large media files

## Code quality

- Keep functions small and single-responsibility
- Pure logic in `segments.py` / `csvio.py`; ffmpeg only in `ffmpeg.py`
- Add tests for every logic change

## Workflow

- Conventional Commits
- `pre-commit run --all-files` + `pytest` before push
- Update CHANGELOG with behaviour changes
