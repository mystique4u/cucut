"""ffmpeg / ffprobe wrappers."""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable

from cucut.segments import Interval

FREEZE_START = re.compile(r"lavfi\.freezedetect\.freeze_start:\s*([\d.]+)")
FREEZE_END = re.compile(r"lavfi\.freezedetect\.freeze_end:\s*([\d.]+)")
DURATION_LINE = re.compile(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)")
TIME_LINE = re.compile(r"time=(\d{2}):(\d{2}):(\d{2}\.\d+)")


class FFmpegNotFoundError(RuntimeError):
    pass


def require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FFmpegNotFoundError("ffmpeg not found in PATH")
    return path


def require_ffprobe() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise FFmpegNotFoundError("ffprobe not found in PATH")
    return path


def parse_hms(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def probe_duration(path: str) -> float:
    require_ffprobe()
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def detect_freezes(
    path: str,
    *,
    noise_db: float = -60.0,
    min_duration: float = 3.0,
    hwaccel: str | None = None,
    scale_width: int | None = None,
    sample_fps: float | None = None,
    ss: float | None = None,
    to: float | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> list[Interval]:
    """Run ffmpeg freezedetect and return frozen intervals (absolute file time)."""
    require_ffmpeg()

    filters: list[str] = []
    if scale_width:
        filters.append(f"scale={scale_width}:-2")
    if sample_fps:
        filters.append(f"fps={sample_fps}")
    filters.append(f"freezedetect=n={noise_db}dB:d={min_duration}")

    cmd = ["ffmpeg", "-hide_banner"]
    if hwaccel:
        cmd.extend(["-hwaccel", hwaccel])
    if ss is not None:
        cmd.extend(["-ss", f"{ss:.6f}"])
    cmd.extend(["-i", path])
    if to is not None:
        cmd.extend(["-to", f"{to:.6f}"])
    cmd.extend(
        [
            "-map",
            "0:v:0",
            "-vf",
            ",".join(filters),
            "-f",
            "null",
            "-",
        ]
    )

    time_offset = ss or 0.0
    clip_duration = (to - ss) if (ss is not None and to is not None) else None

    proc = subprocess.Popen(
        cmd,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
    )
    assert proc.stderr is not None

    freezes: list[Interval] = []
    freeze_start: float | None = None
    total: float | None = None

    for line in proc.stderr:
        if total is None:
            match = DURATION_LINE.search(line)
            if match:
                total = parse_hms(f"{match.group(1)}:{match.group(2)}:{match.group(3)}")

        if on_progress and total:
            match = TIME_LINE.search(line)
            if match:
                current = parse_hms(f"{match.group(1)}:{match.group(2)}:{match.group(3)}")
                if clip_duration:
                    on_progress(min(100.0, current / clip_duration * 100.0))
                else:
                    on_progress(min(100.0, current / total * 100.0))

        match = FREEZE_START.search(line)
        if match:
            freeze_start = float(match.group(1))
            continue

        match = FREEZE_END.search(line)
        if match and freeze_start is not None:
            freeze_end = float(match.group(1)) + time_offset
            freezes.append(Interval(freeze_start + time_offset, freeze_end))
            freeze_start = None

    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg freezedetect failed for {path} (exit {proc.returncode})")

    return freezes


def concat_keep_regions(
    input_path: str,
    output_path: str,
    keep: list[Interval],
    *,
    on_progress: Callable[[float], None] | None = None,
) -> None:
    """Lossless trim via concat demuxer inpoint/outpoint (speedrun-style)."""
    require_ffmpeg()
    if not keep:
        raise ValueError("no keep intervals")

    import os
    import tempfile

    abs_input = os.path.abspath(input_path)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
        concat_path = handle.name
        for region in keep:
            handle.write(f"file '{abs_input}'\n")
            handle.write(f"inpoint {region.start:.6f}\n")
            handle.write(f"outpoint {region.end:.6f}\n")

    try:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_path,
            "-c",
            "copy",
            output_path,
        ]
        proc = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True,
        )
        assert proc.stderr is not None

        total: float | None = None
        for line in proc.stderr:
            if total is None:
                match = DURATION_LINE.search(line)
                if match:
                    total = parse_hms(f"{match.group(1)}:{match.group(2)}:{match.group(3)}")

            if on_progress and total:
                match = TIME_LINE.search(line)
                if match:
                    current = parse_hms(f"{match.group(1)}:{match.group(2)}:{match.group(3)}")
                    on_progress(min(100.0, current / total * 100.0))

        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed (exit {proc.returncode})")
    finally:
        os.unlink(concat_path)
