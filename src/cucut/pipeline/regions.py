"""Merge scan windows for fine-pass region scans."""

from __future__ import annotations

from cucut.csvio import SegmentRow
from cucut.segments import Interval, merge_overlapping


def windows_from_rows(
    rows: list[SegmentRow],
    file_duration: float,
    *,
    pad_sec: float,
) -> list[Interval]:
    """Build merged scan windows from prior-stage segment hits."""
    if not rows:
        return [Interval(0.0, file_duration)]

    raw = [
        Interval(
            max(0.0, row.seg_start - pad_sec),
            min(file_duration, row.seg_end + pad_sec),
        )
        for row in rows
    ]
    return merge_overlapping(raw)
