"""Lossless trim from reviewed CSV."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cucut.csvio import SegmentRow, group_by_path, read_segments
from cucut.ffmpeg import concat_keep_regions, probe_duration
from cucut.segments import Interval, invert_intervals, total_duration


@dataclass(slots=True)
class TrimResult:
    input_path: Path
    output_path: Path
    removed_sec: float
    kept_sec: float
    skipped: bool = False
    reason: str = ""


def rows_to_remove(rows: list[SegmentRow]) -> list[Interval]:
    remove: list[Interval] = []
    for row in rows:
        if row.action == "remove":
            remove.append(Interval(row.seg_start, row.seg_end))
        elif row.action == "keep":
            continue
        elif row.action == "review":
            continue
    return remove


def default_output_path(input_path: Path, output_dir: Path | None) -> Path:
    stem = input_path.stem
    suffix = input_path.suffix
    name = f"{stem}.trimmed{suffix}"
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / name
    return input_path.with_name(name)


def trim_file(
    input_path: Path,
    remove_rows: list[SegmentRow],
    output_path: Path,
    *,
    dry_run: bool = False,
    on_progress: Callable[[float], None] | None = None,
) -> TrimResult:
    file_duration = probe_duration(str(input_path))
    remove = rows_to_remove(remove_rows)
    keep = invert_intervals(remove, file_duration)

    removed = total_duration(
        [Interval(r.seg_start, r.seg_end) for r in remove_rows if r.action == "remove"]
    )
    kept = total_duration(keep)

    if not remove:
        return TrimResult(
            input_path=input_path,
            output_path=output_path,
            removed_sec=0.0,
            kept_sec=file_duration,
            skipped=True,
            reason="no segments marked remove",
        )

    if not keep:
        return TrimResult(
            input_path=input_path,
            output_path=output_path,
            removed_sec=removed,
            kept_sec=0.0,
            skipped=True,
            reason="all content would be removed",
        )

    if dry_run:
        return TrimResult(
            input_path=input_path,
            output_path=output_path,
            removed_sec=removed,
            kept_sec=kept,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_keep_regions(str(input_path), str(output_path), keep, on_progress=on_progress)

    return TrimResult(
        input_path=input_path,
        output_path=output_path,
        removed_sec=removed,
        kept_sec=kept,
    )


def trim_from_csv(
    csv_path: Path,
    *,
    output_dir: Path | None = None,
    dry_run: bool = False,
    on_file: Callable[[Path, TrimResult], None] | None = None,
) -> list[TrimResult]:
    rows = read_segments(csv_path)
    grouped = group_by_path(rows)
    results: list[TrimResult] = []

    for path_str, file_rows in grouped.items():
        input_path = Path(path_str)
        if not input_path.exists():
            result = TrimResult(
                input_path=input_path,
                output_path=default_output_path(input_path, output_dir),
                removed_sec=0.0,
                kept_sec=0.0,
                skipped=True,
                reason="file not found",
            )
            results.append(result)
            if on_file:
                on_file(input_path, result)
            continue

        output_path = default_output_path(input_path, output_dir)
        result = trim_file(input_path, file_rows, output_path, dry_run=dry_run)
        results.append(result)
        if on_file:
            on_file(input_path, result)

    return results


def copy_unmodified(input_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_path, output_path)
