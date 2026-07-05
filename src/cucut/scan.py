"""Batch scan for frozen segments."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from cucut.csvio import SegmentRow, write_segments
from cucut.ffmpeg import detect_freezes, probe_duration

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm"}


def iter_videos(root: Path, *, recursive: bool) -> Iterable[Path]:
    if root.is_file():
        yield root
        return

    pattern = "**/*" if recursive else "*"
    for path in sorted(root.glob(pattern)):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            yield path


def scan_path(
    path: Path,
    *,
    noise_db: float,
    min_duration: float,
    on_progress: Callable[[float], None] | None = None,
) -> list[SegmentRow]:
    file_duration = probe_duration(str(path))

    freezes = detect_freezes(
        str(path),
        noise_db=noise_db,
        min_duration=min_duration,
        on_progress=on_progress,
    )

    return [
        SegmentRow.from_freeze(
            str(path.resolve()),
            freeze.start,
            freeze.end,
            file_duration,
            min_duration=min_duration,
        )
        for freeze in freezes
    ]


def scan_directory(
    root: Path,
    output: Path,
    *,
    noise_db: float = -60.0,
    min_duration: float = 3.0,
    recursive: bool = True,
    on_file: Callable[..., None] | None = None,
) -> list[SegmentRow]:
    videos = list(iter_videos(root, recursive=recursive))
    all_rows: list[SegmentRow] = []

    for index, video in enumerate(videos, start=1):
        if on_file:
            on_file(video, index, len(videos))

        total_videos = len(videos)

        def make_progress(
            v: Path = video,
            i: int = index,
            n: int = total_videos,
        ) -> Callable[[float], None] | None:
            if not on_file:
                return None
            return lambda pct: on_file(v, i, n, pct)

        rows = scan_path(
            video,
            noise_db=noise_db,
            min_duration=min_duration,
            on_progress=make_progress(),
        )
        all_rows.extend(rows)

    write_segments(output, all_rows)
    return all_rows
