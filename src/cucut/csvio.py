"""Review CSV read/write."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

CSV_FIELDS = [
    "path",
    "seg_start",
    "seg_end",
    "duration",
    "dead_sec",
    "confidence",
    "action",
    "reviewed",
]

ACTIONS = frozenset({"remove", "keep", "review"})
CONFIDENCE = frozenset({"high", "medium", "low"})


@dataclass(slots=True)
class SegmentRow:
    path: str
    seg_start: float
    seg_end: float
    duration: float
    dead_sec: float
    confidence: str
    action: str
    reviewed: str

    @classmethod
    def from_freeze(
        cls,
        path: str,
        seg_start: float,
        seg_end: float,
        file_duration: float,
        *,
        min_duration: float,
    ) -> SegmentRow:
        dead_sec = seg_end - seg_start
        confidence = classify_confidence(dead_sec, file_duration, min_duration)
        action = "remove" if confidence == "high" else "review"
        return cls(
            path=path,
            seg_start=seg_start,
            seg_end=seg_end,
            duration=file_duration,
            dead_sec=dead_sec,
            confidence=confidence,
            action=action,
            reviewed="no",
        )


def classify_confidence(dead_sec: float, file_duration: float, min_duration: float) -> str:
    if dead_sec >= max(10.0, min_duration * 2):
        return "high"
    if dead_sec >= min_duration * 1.25 or (file_duration and dead_sec / file_duration >= 0.15):
        return "medium"
    return "low"


def write_segments(path: Path, rows: list[SegmentRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "path": row.path,
                    "seg_start": f"{row.seg_start:.3f}",
                    "seg_end": f"{row.seg_end:.3f}",
                    "duration": f"{row.duration:.3f}",
                    "dead_sec": f"{row.dead_sec:.3f}",
                    "confidence": row.confidence,
                    "action": row.action,
                    "reviewed": row.reviewed,
                }
            )


def read_segments(path: Path) -> list[SegmentRow]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = set(CSV_FIELDS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV missing columns: {', '.join(sorted(missing))}")

        rows: list[SegmentRow] = []
        for index, raw in enumerate(reader, start=2):
            action = raw["action"].strip().lower()
            if action not in ACTIONS:
                raise ValueError(f"line {index}: invalid action {action!r}")
            confidence = raw["confidence"].strip().lower()
            if confidence not in CONFIDENCE:
                raise ValueError(f"line {index}: invalid confidence {confidence!r}")

            rows.append(
                SegmentRow(
                    path=raw["path"].strip(),
                    seg_start=float(raw["seg_start"]),
                    seg_end=float(raw["seg_end"]),
                    duration=float(raw["duration"]),
                    dead_sec=float(raw["dead_sec"]),
                    confidence=confidence,
                    action=action,
                    reviewed=raw["reviewed"].strip().lower(),
                )
            )
        return rows


def group_by_path(rows: list[SegmentRow]) -> dict[str, list[SegmentRow]]:
    grouped: dict[str, list[SegmentRow]] = {}
    for row in rows:
        grouped.setdefault(row.path, []).append(row)
    return grouped
