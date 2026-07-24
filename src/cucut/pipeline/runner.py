"""Multi-pass scan orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from cucut.csvio import SegmentRow, write_segments
from cucut.ffmpeg import VideoUnreadableError, detect_freezes, probe_duration
from cucut.pipeline.hwaccel import resolve_hwaccel
from cucut.pipeline.regions import windows_from_rows
from cucut.pipeline.stages import DEFAULT_PIPELINE, ScanStage
from cucut.scan import iter_videos
from cucut.segments import Interval


@dataclass(slots=True)
class PipelineResult:
    coarse_rows: list[SegmentRow] = field(default_factory=list)
    medium_rows: list[SegmentRow] = field(default_factory=list)
    fine_rows: list[SegmentRow] = field(default_factory=list)
    candidate_files: list[Path] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)
    coarse_csv: Path | None = None
    medium_csv: Path | None = None
    fine_csv: Path | None = None
    segments_csv: Path | None = None


def _unique_paths(rows: list[SegmentRow]) -> list[Path]:
    seen: set[str] = set()
    paths: list[Path] = []
    for row in rows:
        if row.path not in seen:
            seen.add(row.path)
            paths.append(Path(row.path))
    return paths


def _scan_file_stage(
    video: Path,
    stage: ScanStage,
    *,
    hwaccel: str | None,
    prior_rows: list[SegmentRow] | None,
    on_progress: Callable[[float], None] | None,
) -> list[SegmentRow]:
    path_str = str(video.resolve())
    file_duration = probe_duration(path_str)
    prior_for_file = [r for r in (prior_rows or []) if r.path == path_str]

    if stage.region_pad_sec > 0 and prior_for_file:
        windows = windows_from_rows(prior_for_file, file_duration, pad_sec=stage.region_pad_sec)
    else:
        windows = [Interval(0.0, file_duration)]

    rows: list[SegmentRow] = []
    for window in windows:
        full_file = window.start <= 0.0 and window.end >= file_duration - 0.05
        freezes = detect_freezes(
            path_str,
            noise_db=stage.noise_db,
            min_duration=stage.min_duration,
            hwaccel=hwaccel,
            scale_width=stage.scale_width,
            sample_fps=stage.sample_fps,
            ss=None if full_file else window.start,
            to=None if full_file else window.end,
            file_end=file_duration if full_file else window.end,
            on_progress=on_progress,
        )
        for freeze in freezes:
            rows.append(
                SegmentRow.from_freeze(
                    path_str,
                    freeze.start,
                    freeze.end,
                    file_duration,
                    min_duration=stage.min_duration,
                )
            )
    return rows


def _scan_videos(
    videos: list[Path],
    stage: ScanStage,
    *,
    hwaccel: str | None,
    prior_rows: list[SegmentRow] | None,
    on_file: Callable[..., None] | None,
    on_skip: Callable[[str, Path, str], None] | None,
    checkpoint: Path | None,
) -> tuple[list[SegmentRow], list[tuple[Path, str]]]:
    all_rows: list[SegmentRow] = []
    skipped: list[tuple[Path, str]] = []
    total = len(videos)

    for index, video in enumerate(videos, start=1):
        if on_file:
            on_file(stage.name, video, index, total)

        def make_progress(
            v: Path = video,
            i: int = index,
            n: int = total,
            stage_name: str = stage.name,
        ) -> Callable[[float], None] | None:
            if not on_file:
                return None
            return lambda pct: on_file(stage_name, v, i, n, pct)

        try:
            rows = _scan_file_stage(
                video,
                stage,
                hwaccel=hwaccel,
                prior_rows=prior_rows,
                on_progress=make_progress(),
            )
        except VideoUnreadableError as exc:
            reason = str(exc)
            skipped.append((video, reason))
            if on_skip:
                on_skip(stage.name, video, reason)
            continue

        all_rows.extend(rows)
        if checkpoint is not None:
            write_segments(checkpoint, all_rows)

    return all_rows, skipped


def run_pipeline(
    root: Path,
    output_dir: Path,
    *,
    stages: tuple[ScanStage, ...] = DEFAULT_PIPELINE,
    prefer_gpu: bool = True,
    recursive: bool = True,
    on_file: Callable[..., None] | None = None,
    on_skip: Callable[[str, Path, str], None] | None = None,
) -> PipelineResult:
    """Run coarse → medium → fine pipeline. Each pass narrows candidates."""
    output_dir.mkdir(parents=True, exist_ok=True)
    hwaccel = resolve_hwaccel(prefer_gpu=prefer_gpu)

    all_videos = list(iter_videos(root, recursive=recursive))
    if not all_videos:
        raise FileNotFoundError(f"No video files under {root}")

    result = PipelineResult()
    prior_rows: list[SegmentRow] | None = None
    candidates = all_videos

    for stage in stages:
        if stage.name == "coarse":
            targets = all_videos
        else:
            if not prior_rows:
                break
            candidates = _unique_paths(prior_rows)
            targets = [p for p in candidates if p.exists()]
            if not targets:
                break

        out_path = output_dir / f"{stage.name}.csv"
        rows, skipped = _scan_videos(
            targets,
            stage,
            hwaccel=hwaccel,
            prior_rows=prior_rows,
            on_file=on_file,
            on_skip=on_skip,
            checkpoint=out_path,
        )
        result.skipped.extend(skipped)
        write_segments(out_path, rows)

        if stage.name == "coarse":
            result.coarse_rows = rows
            result.coarse_csv = out_path
        elif stage.name == "medium":
            result.medium_rows = rows
            result.medium_csv = out_path
        elif stage.name == "fine":
            result.fine_rows = rows
            result.fine_csv = out_path
        prior_rows = rows

    final_rows = prior_rows or []
    segments_path = output_dir / "segments.csv"
    write_segments(segments_path, final_rows)

    if result.coarse_rows:
        candidates_path = output_dir / "candidates.txt"
        candidates_path.write_text(
            "\n".join(str(p) for p in _unique_paths(result.coarse_rows)) + "\n",
            encoding="utf-8",
        )
        result.candidate_files = _unique_paths(result.coarse_rows)

    if result.skipped:
        skipped_path = output_dir / "skipped.txt"
        skipped_path.write_text(
            "\n".join(f"{path}\t{reason}" for path, reason in result.skipped) + "\n",
            encoding="utf-8",
        )

    result.segments_csv = segments_path
    return result
