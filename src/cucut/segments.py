"""Time interval helpers (invert dead → keep)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Interval:
    start: float
    end: float

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"invalid interval: {self.start} > {self.end}")

    @property
    def duration(self) -> float:
        return self.end - self.start


def merge_overlapping(intervals: list[Interval], *, gap: float = 0.0) -> list[Interval]:
    """Merge intervals that overlap or are within `gap` seconds."""
    if not intervals:
        return []

    ordered = sorted(intervals, key=lambda i: i.start)
    merged: list[Interval] = [ordered[0]]

    for current in ordered[1:]:
        prev = merged[-1]
        if current.start <= prev.end + gap:
            merged[-1] = Interval(prev.start, max(prev.end, current.end))
        else:
            merged.append(current)

    return merged


def invert_intervals(
    remove: list[Interval],
    total_duration: float,
    *,
    min_keep: float = 0.05,
) -> list[Interval]:
    """Return keep intervals by subtracting remove intervals from [0, total_duration]."""
    if total_duration <= 0:
        return []

    dead = merge_overlapping(remove)
    keep: list[Interval] = []
    cursor = 0.0

    for segment in dead:
        start = max(0.0, segment.start)
        end = min(total_duration, segment.end)
        if start > cursor and start - cursor >= min_keep:
            keep.append(Interval(cursor, start))
        cursor = max(cursor, end)

    if total_duration - cursor >= min_keep:
        keep.append(Interval(cursor, total_duration))

    return keep


def total_duration(intervals: list[Interval]) -> float:
    return sum(i.duration for i in intervals)
