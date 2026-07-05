"""Export segments for LosslessCut."""

from __future__ import annotations

import csv
from pathlib import Path

from cucut.csvio import SegmentRow, group_by_path, read_segments
from cucut.ffmpeg import probe_duration
from cucut.segments import Interval, invert_intervals


def _losslesscut_rows(
    segments: list[tuple[float, float, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for start, end, label in segments:
        rows.append(
            {
                "Start": f"{start:.6f}",
                "End": f"{end:.6f}",
                "Name": label,
            }
        )
    return rows


def dead_segments_for_file(rows: list[SegmentRow]) -> list[tuple[float, float, str]]:
    out: list[tuple[float, float, str]] = []
    for row in rows:
        if row.action == "keep":
            continue
        label = f"dead {row.seg_start:.1f}-{row.seg_end:.1f} ({row.confidence}, {row.action})"
        out.append((row.seg_start, row.seg_end, label))
    return out


def keep_segments_for_file(
    rows: list[SegmentRow],
    file_duration: float,
) -> list[tuple[float, float, str]]:
    remove = [Interval(row.seg_start, row.seg_end) for row in rows if row.action == "remove"]
    keep = invert_intervals(remove, file_duration)
    return [(segment.start, segment.end, f"keep {index + 1}") for index, segment in enumerate(keep)]


def export_losslesscut(
    csv_path: Path,
    output_dir: Path,
    *,
    mode: str = "dead",
) -> list[Path]:
    """Write per-file LosslessCut CSV (Start,End,Name header)."""
    if mode not in {"dead", "keep"}:
        raise ValueError("mode must be 'dead' or 'keep'")

    rows = read_segments(csv_path)
    grouped = group_by_path(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for path_str, file_rows in grouped.items():
        input_path = Path(path_str)
        stem = input_path.stem
        out_path = output_dir / f"{stem}.losslesscut.csv"

        if mode == "dead":
            segments = dead_segments_for_file(file_rows)
        else:
            duration = file_rows[0].duration if file_rows else probe_duration(str(input_path))
            segments = keep_segments_for_file(file_rows, duration)

        if not segments:
            continue

        with out_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["Start", "End", "Name"])
            writer.writeheader()
            writer.writerows(_losslesscut_rows(segments))

        written.append(out_path)

    return written
