"""Cucut CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cucut import __version__
from cucut.export import export_losslesscut
from cucut.ffmpeg import FFmpegNotFoundError
from cucut.gui import GuiToolNotFoundError, launch
from cucut.pipeline import run_pipeline
from cucut.pipeline.stages import (
    DJI_PIPELINE,
    STAGE_COARSE,
    STAGE_COARSE_DJI,
    STAGE_FINE,
    STAGE_FINE_DJI,
    STAGE_MEDIUM,
    STAGE_MEDIUM_DJI,
    ScanStage,
)
from cucut.presets import PRESETS
from cucut.scan import scan_directory
from cucut.trim import trim_from_csv


def _format_sec(value: float) -> str:
    minutes, seconds = divmod(value, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{int(hours):d}:{int(minutes):02d}:{seconds:05.2f}"
    return f"{int(minutes):d}:{seconds:05.2f}"


def cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.input).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()

    from cucut.presets import PRESETS

    mode = "fast" if args.fast and args.mode == "default" else args.mode
    preset = PRESETS[mode]

    noise_db = preset.noise_db if args.noise is None else args.noise
    min_duration = preset.min_duration if args.min_duration is None else args.min_duration
    hwaccel = args.hwaccel
    if hwaccel is None and preset.prefer_hwaccel:
        hwaccel = "auto"
    scale_width = preset.scale_width if args.scale_width is None else args.scale_width
    sample_fps = preset.sample_fps if args.sample_fps is None else args.sample_fps

    def on_file(video: Path, index: int, total: int, pct: float | None = None) -> None:
        if pct is None:
            print(f"[{index}/{total}] scanning {video.name} [{mode}]", flush=True)
        elif args.verbose:
            print(f"  {video.name}: {pct:.0f}%", flush=True)

    rows, file_count = scan_directory(
        root,
        output,
        noise_db=noise_db,
        min_duration=min_duration,
        hwaccel=hwaccel,
        scale_width=scale_width,
        sample_fps=sample_fps,
        recursive=not args.no_recursive,
        on_file=on_file,
    )

    print(f"Wrote {len(rows)} dead segment(s) from {file_count} file(s) → {output}")
    if not rows:
        print(
            "No freezes detected. Try --mode dji (mostly-static camera), "
            "or --noise -20 / lower --min-duration."
        )
    return 0


def cmd_trim(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None

    def on_file(path: Path, result) -> None:
        if result.skipped:
            print(f"SKIP {path.name}: {result.reason}")
            return
        prefix = "DRY-RUN" if args.dry_run else "OK"
        print(
            f"{prefix} {path.name} → {result.output_path.name} "
            f"(kept {_format_sec(result.kept_sec)}, removed {_format_sec(result.removed_sec)})"
        )

    results = trim_from_csv(
        csv_path,
        output_dir=output_dir,
        dry_run=args.dry_run,
        on_file=on_file,
    )
    done = sum(1 for r in results if not r.skipped)
    print(f"Processed {done}/{len(results)} file(s)")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    written = export_losslesscut(csv_path, output_dir, mode=args.mode)
    if not written:
        print("No segments to export (check action column).")
        return 0

    print(f"Wrote {len(written)} LosslessCut CSV file(s) → {output_dir}")
    for path in written:
        print(f"  {path.name}")
    print("\nLosslessCut: File → Import project → CSV")
    if args.mode == "dead":
        print("Tip: dead segments are for review; use --mode keep before final export.")
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    video = Path(args.video).expanduser().resolve() if args.video else None
    csv = Path(args.csv).expanduser().resolve() if args.csv else None
    return launch(args.tool, video=video, csv=csv)


def cmd_review(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv).expanduser().resolve()
    try:
        from cucut.web import serve_review
    except ImportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("Install with: pip install 'cucut[web]'", file=sys.stderr)
        return 2
    serve_review(csv_path, host=args.host, port=args.port)
    return 0


_STAGE_BY_NAME = {
    "coarse": STAGE_COARSE,
    "medium": STAGE_MEDIUM,
    "fine": STAGE_FINE,
}

_STAGE_BY_NAME_DJI = {
    "coarse": STAGE_COARSE_DJI,
    "medium": STAGE_MEDIUM_DJI,
    "fine": STAGE_FINE_DJI,
}


def cmd_pipeline(args: argparse.Namespace) -> int:
    root = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()

    stage_map = _STAGE_BY_NAME_DJI if args.mode == "dji" else _STAGE_BY_NAME
    if args.stages:
        stages: tuple[ScanStage, ...] = tuple(stage_map[name] for name in args.stages)
    elif args.mode == "dji":
        stages = DJI_PIPELINE
    else:
        stages = (STAGE_COARSE, STAGE_MEDIUM, STAGE_FINE)

    def on_file(
        stage: str,
        video: Path,
        index: int,
        total: int,
        pct: float | None = None,
    ) -> None:
        prefix = f"[{stage} {index}/{total}]"
        if pct is None:
            print(f"{prefix} {video.name}", flush=True)
        elif args.verbose:
            print(f"  {video.name}: {pct:.0f}%", flush=True)

    def on_skip(stage: str, video: Path, reason: str) -> None:
        print(f"SKIP [{stage}] {video.name}: {reason}", flush=True)

    result = run_pipeline(
        root,
        output_dir,
        stages=stages,
        prefer_gpu=not args.no_gpu,
        recursive=not args.no_recursive,
        on_file=on_file,
        on_skip=on_skip,
    )

    print(f"\nPipeline output → {output_dir}")
    if result.coarse_csv:
        print(f"  coarse:    {result.coarse_csv.name} ({len(result.coarse_rows)} hit(s))")
    if result.medium_csv:
        print(f"  medium:    {result.medium_csv.name} ({len(result.medium_rows)} hit(s))")
    if result.fine_csv:
        print(f"  fine:      {result.fine_csv.name} ({len(result.fine_rows)} hit(s))")
    if result.segments_csv:
        print(f"  review:    {result.segments_csv.name}")
    if result.candidate_files:
        print(f"  flagged:   {len(result.candidate_files)} file(s) after coarse pass")
    if result.skipped:
        print(f"  skipped:   {len(result.skipped)} unreadable file(s) → skipped.txt")

    if not result.coarse_rows and "coarse" in {s.name for s in stages}:
        threshold = 8 if args.mode == "dji" else 12
        print(
            f"\nNo long freezes in coarse pass. " f"Folder looks clean (≥{threshold} s threshold)."
        )
    elif len(result.coarse_rows) and not (result.medium_rows or result.fine_rows):
        if any(s.name in {"medium", "fine"} for s in stages):
            print("\nCoarse hits did not survive medium/fine passes — check coarse.csv.")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cucut",
        description=(
            "Detect and trim frozen/dead segments in video (ffmpeg freezedetect, lossless copy)."
        ),
    )
    parser.add_argument("--version", action="version", version=f"cucut {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan folder/file for freeze segments → review CSV")
    scan.add_argument("input", help="Video file or directory")
    scan.add_argument(
        "-o",
        "--output",
        default="segments.csv",
        help="Output CSV path (default: segments.csv)",
    )
    scan.add_argument(
        "--mode",
        choices=list(PRESETS),
        default="default",
        help="Detect preset: default (-60dB), fast (downscale), dji (mostly-static / -20dB)",
    )
    scan.add_argument(
        "--noise",
        type=float,
        default=None,
        help="freezedetect noise in dB (default: from --mode, else -60)",
    )
    scan.add_argument(
        "--min-duration",
        type=float,
        default=None,
        help="Minimum freeze length in seconds (default: from --mode, else 5)",
    )
    scan.add_argument(
        "--fast",
        action="store_true",
        help="Alias for --mode fast (hwaccel auto + scale 480px + 3 fps)",
    )
    scan.add_argument(
        "--hwaccel",
        default=None,
        help="ffmpeg hwaccel mode (e.g. auto, vaapi). Used alone or with --fast",
    )
    scan.add_argument(
        "--scale-width",
        type=int,
        default=None,
        help="Downscale width before detect (e.g. 480). Used alone or with --fast",
    )
    scan.add_argument(
        "--sample-fps",
        type=float,
        default=None,
        help="Sample FPS before detect (e.g. 3). Used alone or with --fast",
    )
    scan.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not scan subdirectories",
    )
    scan.add_argument("-v", "--verbose", action="store_true")
    scan.set_defaults(func=cmd_scan)

    pipeline = sub.add_parser(
        "pipeline",
        help="Multi-pass scan: coarse (fast) → medium → fine on candidates",
    )
    pipeline.add_argument("input", help="Video file or directory")
    pipeline.add_argument(
        "-o",
        "--output",
        default="pipeline-out",
        help="Output directory for stage CSVs (default: pipeline-out/)",
    )
    pipeline.add_argument(
        "--mode",
        choices=["default", "dji"],
        default="default",
        help="Stage presets: default (strict) or dji (mostly-static / -20dB)",
    )
    pipeline.add_argument(
        "--stages",
        nargs="+",
        choices=["coarse", "medium", "fine"],
        metavar="STAGE",
        help="Run subset of passes (default: all three)",
    )
    pipeline.add_argument(
        "--no-gpu",
        action="store_true",
        help="Software decode only (no hwaccel)",
    )
    pipeline.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not scan subdirectories",
    )
    pipeline.add_argument("-v", "--verbose", action="store_true")
    pipeline.set_defaults(func=cmd_pipeline)

    trim = sub.add_parser("trim", help="Lossless trim from reviewed CSV")
    trim.add_argument("csv", help="Review CSV from scan")
    trim.add_argument(
        "-o",
        "--output-dir",
        help="Output directory (default: same folder as source, *.trimmed.mp4)",
    )
    trim.add_argument("--dry-run", action="store_true", help="Show plan without ffmpeg")
    trim.set_defaults(func=cmd_trim)

    review = sub.add_parser(
        "review",
        help="Local web UI to accept/reject CSV segments before trim",
    )
    review.add_argument("csv", help="Review CSV from scan/pipeline")
    review.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    review.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    review.set_defaults(func=cmd_review)

    export = sub.add_parser("export", help="Export LosslessCut CSV per file")
    export.add_argument("csv", help="Review CSV")
    export.add_argument(
        "-o",
        "--output-dir",
        default="losslesscut",
        help="Output directory (default: losslesscut/)",
    )
    export.add_argument(
        "--mode",
        choices=["dead", "keep"],
        default="dead",
        help="dead=review freezes; keep=segments to export after review (default: dead)",
    )
    export.set_defaults(func=cmd_export)

    gui = sub.add_parser("gui", help="Launch LosslessCut or frame-checker")
    gui.add_argument(
        "--tool",
        choices=["losslesscut", "frame-checker"],
        default="losslesscut",
        help="GUI to launch (default: losslesscut)",
    )
    gui.add_argument("video", nargs="?", help="Optional video to open")
    gui.add_argument("--csv", help="Review CSV (export first for LosslessCut import)")
    gui.set_defaults(func=cmd_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.func(args)
    except FFmpegNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except GuiToolNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
