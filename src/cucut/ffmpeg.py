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


class VideoUnreadableError(RuntimeError):
    """Video exists but ffprobe/ffmpeg cannot read it (corrupt, incomplete, etc.)."""


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
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "ffprobe failed").strip().splitlines()
        message = detail[-1] if detail else "ffprobe failed"
        raise VideoUnreadableError(f"{path}: {message}")
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise VideoUnreadableError(f"{path}: invalid duration {result.stdout!r}") from exc


def close_open_freeze(
    freezes: list[Interval],
    freeze_start: float | None,
    *,
    time_offset: float,
    last_time: float | None,
    file_end: float | None,
    to: float | None,
) -> list[Interval]:
    """If freezedetect left an open freeze_start (common at EOF), close it.

    ffmpeg often omits freeze_end when the freeze lasts until the end of the file.
    """
    if freeze_start is None:
        return freezes

    abs_start = freeze_start + time_offset
    candidates: list[float] = []
    if last_time is not None:
        candidates.append(last_time + time_offset)
    if to is not None:
        candidates.append(to)
    if file_end is not None:
        candidates.append(file_end)

    if not candidates:
        return freezes

    abs_end = max(candidates)
    if abs_end > abs_start + 0.05:
        freezes.append(Interval(abs_start, abs_end))
    return freezes


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
    file_end: float | None = None,
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
    last_time: float | None = None

    for line in proc.stderr:
        if total is None:
            match = DURATION_LINE.search(line)
            if match:
                total = parse_hms(f"{match.group(1)}:{match.group(2)}:{match.group(3)}")

        match = TIME_LINE.search(line)
        if match:
            last_time = parse_hms(f"{match.group(1)}:{match.group(2)}:{match.group(3)}")
            if on_progress and total:
                if clip_duration:
                    on_progress(min(100.0, last_time / clip_duration * 100.0))
                else:
                    on_progress(min(100.0, last_time / total * 100.0))

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

    return close_open_freeze(
        freezes,
        freeze_start,
        time_offset=time_offset,
        last_time=last_time,
        file_end=file_end,
        to=to,
    )


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
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, dir=cucut_tmp_dir()
    ) as handle:
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


def cucut_tmp_dir() -> str:
    """Scratch dir for cuts/proxies. Prefer FAST/info — never fill root ``/``."""
    import os
    from pathlib import Path

    override = os.environ.get("CUCUT_TMPDIR") or os.environ.get("CUCUT_TMP")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override))
    candidates.extend(
        [
            Path("/mnt/FAST/cucut-tmp"),
            Path("/run/media/optimus/info/cucut/tmp"),
        ]
    )
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            if os.access(path, os.W_OK):
                return str(path)
        except OSError:
            continue
    # Last resort: beside cwd (still better than filling /tmp on a full root disk)
    fallback = Path.cwd() / ".cucut-tmp"
    fallback.mkdir(parents=True, exist_ok=True)
    return str(fallback)


def proxy_cache_dir() -> str:
    """Directory for scrubbing proxies. Prefer FAST mount; else info; else CUCUT_TMP."""
    import os
    from pathlib import Path

    override = os.environ.get("CUCUT_PROXY_DIR")
    if override:
        Path(override).mkdir(parents=True, exist_ok=True)
        return override

    for path in (
        Path("/mnt/FAST/cucut-proxies"),
        Path("/run/media/optimus/info/cucut/proxies"),
        Path(cucut_tmp_dir()) / "proxies",
    ):
        try:
            if path.parent.is_dir() or path == Path(cucut_tmp_dir()) / "proxies":
                path.mkdir(parents=True, exist_ok=True)
                if os.access(path, os.W_OK):
                    return str(path)
        except OSError:
            continue
    raise RuntimeError("No writable proxy cache (set CUCUT_PROXY_DIR or free space on FAST/info)")


# Bump when proxy encode settings change (invalidates old cache names).
_PROXY_VERSION = "v6strip"


def proxy_path_for(source: str, *, cache_dir: str | None = None) -> str:
    """Stable proxy filename keyed by absolute path + size + mtime."""
    import hashlib
    import os
    from pathlib import Path

    src = Path(source).expanduser().resolve()
    st = src.stat()
    key = f"{src}|{st.st_size}|{int(st.st_mtime)}|{_PROXY_VERSION}"
    digest = hashlib.sha1(key.encode()).hexdigest()[:16]
    base = cache_dir or proxy_cache_dir()
    return os.path.join(base, f"{digest}_{src.stem}.{_PROXY_VERSION}.mp4")


def filmstrip_dir_for(source: str, *, cache_dir: str | None = None) -> str:
    """Directory for seek-extracted JPEG scrub thumbs."""
    import hashlib
    import os
    from pathlib import Path

    src = Path(source).expanduser().resolve()
    st = src.stat()
    key = f"strip|{src}|{st.st_size}|{int(st.st_mtime)}|{_PROXY_VERSION}"
    digest = hashlib.sha1(key.encode()).hexdigest()[:16]
    base = cache_dir or proxy_cache_dir()
    return os.path.join(base, "strips", f"{digest}_{src.stem}")


def _run_proxy_ffmpeg(
    cmd: list[str],
    tmp_out: str,
    *,
    on_progress: Callable[[float], None] | None,
) -> None:
    proc = subprocess.Popen(
        cmd,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
    )
    assert proc.stderr is not None
    total: float | None = None
    err_tail: list[str] = []
    for line in proc.stderr:
        err_tail.append(line)
        if len(err_tail) > 30:
            err_tail.pop(0)
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
        import os

        try:
            os.unlink(tmp_out)
        except OSError:
            pass
        detail = "".join(err_tail[-6:]).strip() or f"exit {proc.returncode}"
        raise RuntimeError(f"ffmpeg preview proxy failed: {detail}")


def build_filmstrip(
    source: str,
    *,
    interval: float = 10.0,
    scale_width: int = 160,
    workers: int = 4,
    cache_dir: str | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> dict[str, object]:
    """Extract JPEG thumbs every ``interval`` seconds via seek (fast navigation).

    Does **not** decode the whole timeline — only sparse ``-ss`` grabs.
    """
    import json
    import os
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from pathlib import Path

    require_ffmpeg()
    duration = probe_duration(source)
    out_dir = filmstrip_dir_for(source, cache_dir=cache_dir)
    os.makedirs(out_dir, exist_ok=True)
    meta_path = os.path.join(out_dir, "meta.json")

    times = [round(t, 3) for t in _frange(0.0, duration, interval)]
    # Always include a near-EOF thumb so "Mark Out" on the last tile = delete-to-end.
    end_t = round(max(0.0, duration - 0.05), 3)
    if not times or times[-1] < end_t - 0.2:
        times.append(end_t)
    elif times[-1] < end_t:
        times[-1] = end_t

    def grab(t: float) -> tuple[float, str | None]:
        name = f"{int(t):05d}_{int((t % 1) * 100):02d}.jpg"
        dest = os.path.join(out_dir, name)
        if os.path.isfile(dest) and os.path.getsize(dest) > 0:
            return t, dest
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{t:.3f}",
            "-hwaccel",
            "cuda",
            "-i",
            source,
            "-frames:v",
            "1",
            "-vf",
            f"scale={scale_width}:-2",
            "-q:v",
            "8",
            dest,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0 or not os.path.isfile(dest):
            cmd2 = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{t:.3f}",
                "-i",
                source,
                "-frames:v",
                "1",
                "-vf",
                f"scale={scale_width}:-2",
                "-q:v",
                "8",
                dest,
            ]
            proc = subprocess.run(cmd2, capture_output=True, text=True, check=False)
            if proc.returncode != 0 or not os.path.isfile(dest):
                return t, None
        return t, dest

    frames: list[dict[str, object]] = []
    done = 0
    total = len(times)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(grab, t): t for t in times}
        for fut in as_completed(futures):
            t, path = fut.result()
            done += 1
            if on_progress:
                on_progress(min(100.0, done / total * 100.0))
            if path:
                frames.append({"t": t, "file": os.path.basename(path)})

    frames.sort(key=lambda f: float(f["t"]))  # type: ignore[arg-type]
    meta = {
        "source": str(Path(source).resolve()),
        "duration": duration,
        "interval": interval,
        "frames": frames,
    }
    with open(meta_path, "w", encoding="utf-8") as handle:
        json.dump(meta, handle)
    return meta


def _frange(start: float, stop: float, step: float) -> list[float]:
    values: list[float] = []
    x = start
    if step <= 0:
        return values
    while x <= stop + 1e-9:
        values.append(x)
        x += step
    return values


def ensure_filmstrip(
    source: str,
    *,
    interval: float = 10.0,
    on_progress: Callable[[float], None] | None = None,
) -> dict[str, object]:
    """Return filmstrip meta, building if missing/incomplete."""
    import json
    import os

    out_dir = filmstrip_dir_for(source)
    meta_path = os.path.join(out_dir, "meta.json")
    if os.path.isfile(meta_path):
        with open(meta_path, encoding="utf-8") as handle:
            meta = json.load(handle)
        if meta.get("frames"):
            if on_progress:
                on_progress(100.0)
            return meta
    return build_filmstrip(source, interval=interval, on_progress=on_progress)


def build_preview_proxy(
    source: str,
    output: str,
    *,
    scale_width: int = 320,
    sample_fps: float = 2.0,
    on_progress: Callable[[float], None] | None = None,
) -> None:
    """Optional continuous H.264 proxy — GPU only, no slow software fallback.

    Prefer filmstrip for navigation; this is for playback scrubbing after GPU encode.
    """
    require_ffmpeg()
    import os

    parent = os.path.dirname(os.path.abspath(output)) or "."
    os.makedirs(parent, exist_ok=True)
    tmp_out = f"{output}.partial.mp4"
    vf = f"scale={scale_width}:-2,fps={sample_fps},format=yuv420p"

    # GPU only — software full-file encode is too slow for 4K DJI.
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-hwaccel",
        "cuda",
        "-i",
        source,
        "-map",
        "0:v:0",
        "-vf",
        vf,
        "-c:v",
        "h264_nvenc",
        "-preset",
        "p1",
        "-tune",
        "ll",
        "-rc",
        "constqp",
        "-qp",
        "36",
        "-g",
        "5",
        "-an",
        "-movflags",
        "+faststart",
        tmp_out,
    ]
    _run_proxy_ffmpeg(cmd, tmp_out, on_progress=on_progress)
    os.replace(tmp_out, output)


def ensure_preview_proxy(
    source: str,
    *,
    cache_dir: str | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> str:
    """Return path to an up-to-date scrubbing proxy, building it if missing."""
    import os

    out = proxy_path_for(source, cache_dir=cache_dir)
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        return out
    build_preview_proxy(source, out, on_progress=on_progress)
    return out


def lossless_cut_range(
    source: str,
    output: str,
    start: float,
    end: float,
    *,
    on_progress: Callable[[float], None] | None = None,
) -> None:
    """Lossless keep [start, end) via stream copy into a new file."""
    require_ffmpeg()
    if end <= start:
        raise ValueError("end must be greater than start")
    duration = end - start
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-ss",
        f"{start:.6f}",
        "-i",
        source,
        "-t",
        f"{duration:.6f}",
        "-c",
        "copy",
        "-avoid_negative_ts",
        "make_zero",
        output,
    ]
    proc = subprocess.Popen(
        cmd,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
    )
    assert proc.stderr is not None
    span = end - start
    for line in proc.stderr:
        if on_progress and span > 0:
            match = TIME_LINE.search(line)
            if match:
                current = parse_hms(f"{match.group(1)}:{match.group(2)}:{match.group(3)}")
                on_progress(min(100.0, current / span * 100.0))
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg lossless cut failed (exit {proc.returncode})")


def remove_range_strategy(source: str, start: float, end: float) -> str:
    """Which lossless path ``lossless_remove_range`` will take."""
    duration = probe_duration(source)
    remove_end = min(end, duration)
    remove_start = max(0.0, start)
    if remove_start <= 0.05:
        return "keep-tail"
    # Filmstrip thumbs are every ~10s; last tile was often ~10s before EOF.
    if remove_end >= duration - 12.0:
        return "keep-head"
    return "middle-concat"


def lossless_remove_range(
    source: str,
    output: str,
    start: float,
    end: float,
    *,
    on_progress: Callable[[float], None] | None = None,
) -> None:
    """Lossless delete [start, end) — keep everything outside that window.

    Fast paths (single stream-copy, no concat):
    - delete from start → keep tail with ``-ss end``
    - delete through end → keep head with ``-t start``
    Middle deletes use two parts + concat under ``cucut_tmp_dir()`` (not ``/tmp``).
    """
    import os
    import tempfile

    if end <= start:
        raise ValueError("end must be greater than start")
    duration = probe_duration(source)
    remove_end = min(end, duration)
    remove_start = max(0.0, start)
    if remove_end <= remove_start:
        raise ValueError("remove window is empty after clamping to file duration")
    if remove_start <= 0 and remove_end >= duration:
        raise ValueError("remove window covers the entire file")

    require_ffmpeg()

    # Delete prefix [0, end) → keep [end, duration)
    if remove_start <= 0.05:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-ss",
            f"{remove_end:.6f}",
            "-i",
            source,
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            output,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg keep-tail failed (exit {proc.returncode})")
        if on_progress:
            on_progress(100.0)
        return

    # Delete suffix [start, duration) → keep [0, start)
    # 12s slack matches ~10s filmstrip spacing so last-thumb Out ≈ EOF.
    if remove_end >= duration - 12.0:
        lossless_cut_range(source, output, 0.0, remove_start, on_progress=on_progress)
        return

    # Middle delete — two parts + concat on FAST/info scratch
    parts: list[str] = []
    with tempfile.TemporaryDirectory(prefix="cucut-rm-", dir=cucut_tmp_dir()) as tmp:
        part_a = os.path.join(tmp, "a.mp4")
        lossless_cut_range(source, part_a, 0.0, remove_start)
        parts.append(part_a)

        part_b = os.path.join(tmp, "b.mp4")
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-ss",
            f"{remove_end:.6f}",
            "-i",
            source,
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            part_b,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg tail copy failed (exit {proc.returncode})")
        parts.append(part_b)

        list_path = os.path.join(tmp, "list.txt")
        with open(list_path, "w", encoding="utf-8") as handle:
            for part in parts:
                handle.write(f"file '{part}'\n")
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_path,
            "-c",
            "copy",
            output,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed (exit {proc.returncode})")
        if on_progress:
            on_progress(100.0)
