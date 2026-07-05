# cucut

CLI для поиска «мёртвых» (freeze) участков в DJI/MP4 и lossless-обрезки через ffmpeg.

Двухфазный workflow: **scan → review → trim**. Для GUI-ревью — [LosslessCut](https://github.com/mifi/lossless-cut); для batch-scan с GUI — опционально [frame-checker](https://github.com/kuvk/frame-checker).

## Требования

- Python 3.11+
- ffmpeg / ffprobe в `PATH`

## Установка

```bash
cd ~/dev/repos/cucut
pip install -e .
# или без установки:
pip install -e ".[dev]"
```

## Быстрый старт

```bash
# 1. Скан папки с роликами
cucut scan ~/Videos/DJI -o segments.csv

# 2. Ревью CSV (LibreOffice / VS Code / LosslessCut)
#    action: remove | keep | review
#    high-confidence freeze → remove по умолчанию

# 3. LosslessCut CSV для визуального ревью (опционально)
cucut export segments.csv -o losslesscut/ --mode dead
cucut gui --tool losslesscut --csv losslesscut/DJI_001.losslesscut.csv ~/Videos/DJI/DJI_001.mp4

# 4. Lossless trim (оригиналы не трогаются)
cucut trim segments.csv -o ~/Videos/DJI-trimmed/
```

## Команды

| Команда | Описание |
|---------|----------|
| `cucut scan INPUT` | Batch freezedetect → `segments.csv` |
| `cucut trim CSV` | Вырезать `action=remove`, склеить keep через `-c copy` |
| `cucut export CSV` | LosslessCut CSV (`Start,End,Name`) |
| `cucut gui` | Запуск LosslessCut или frame-checker |

### scan

```bash
cucut scan ~/Videos/DJI -o segments.csv \
  --noise -60 \
  --min-duration 3
```

Параметры `freezedetect` (стартовые): `noise=-60dB`, `min_duration=3s`.

### Review CSV

| path | seg_start | seg_end | duration | dead_sec | confidence | action | reviewed |
|------|-----------|---------|----------|----------|------------|--------|----------|
| DJI_001.mp4 | 98.200 | 142.500 | 600.000 | 44.300 | high | remove | no |

- **duration** — длина файла (сек)
- **dead_sec** — длина freeze-интервала
- **action**: `remove` (вырезать), `keep` (оставить freeze), `review` (решить вручную)

### trim

```bash
cucut trim segments.csv -o ./trimmed/ --dry-run   # план без ffmpeg
cucut trim segments.csv -o ./trimmed/
```

Dead intervals инвертируются в keep; склейка через concat demuxer (`inpoint`/`outpoint`), как в [speedrun](https://github.com/benjaminjackson/speedrun).

**Ограничение:** при `-c copy` точность cut ± keyframe (0.5–2 с). Оригиналы не изменяются; выход: `*.trimmed.mp4`.

### export (LosslessCut)

```bash
cucut export segments.csv -o losslesscut/ --mode dead   # freeze для ревью
cucut export segments.csv -o losslesscut/ --mode keep    # keep-сегменты для экспорта
```

Формат: заголовок `Start,End,Name`, время в секундах — совместимо с LosslessCut import.

### gui

```bash
cucut gui --tool losslesscut DJI_001.mp4
cucut gui --tool frame-checker
```

## Архитектура

```text
scan (freezedetect) → segments.csv → [review] → trim (-c copy concat)
                              ↓
                    export → LosslessCut CSV → gui
```

Вдохновение: [speedrun](https://github.com/benjaminjackson/speedrun) (invert + concat), [deadframe](https://github.com/agatan/deadframe) (детект, `-print`), [frame-checker](https://github.com/kuvk/frame-checker) (batch GUI scan), [LosslessCut](https://github.com/mifi/lossless-cut) (ревью + lossless export).

## Тесты

```bash
pytest
# pre-push hook runs full check on git push — no manual script needed
```

## DevOps и агенты

- [AGENTS.md](AGENTS.md) — entrypoint для Cursor/Continue
- [CONTRIBUTING.md](CONTRIBUTING.md) — workflow, conventional commits
- `git config core.hooksPath .githooks` — pre-commit / pre-push
- Skills: `.agents/skills/` (cucut-*, caveman для экономии токенов)
- CI: `.github/workflows/ci.yml`

## Лицензия

MIT
