"""Cucut CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cucut import __version__
from cucut.export import export_losslesscut
from cucut.ffmpeg import FFmpegNotFoundError
from cucut.gui import GuiToolNotFoundError, launch
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

    def on_file(video: Path, index: int, total: int, pct: float | None = None) -> None:
        if pct is None:
            print(f"[{index}/{total}] scanning {video.name}", flush=True)
        elif args.verbose:
            print(f"  {video.name}: {pct:.0f}%", flush=True)

    rows = scan_directory(
        root,
        output,
        noise_db=args.noise,
        min_duration=args.min_duration,
        recursive=not args.no_recursive,
        on_file=on_file,
    )

    files = {row.path for row in rows}
    print(f"Wrote {len(rows)} dead segment(s) from {len(files)} file(s) → {output}")
    if not rows:
        print("No freezes detected. Try lowering --noise (e.g. -55) or --min-duration.")
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
        "--noise",
        type=float,
        default=-60.0,
        help="freezedetect noise in dB (default: -60, more sensitive than -70)",
    )
    scan.add_argument(
        "--min-duration",
        type=float,
        default=3.0,
        help="Minimum freeze length in seconds (default: 3)",
    )
    scan.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not scan subdirectories",
    )
    scan.add_argument("-v", "--verbose", action="store_true")
    scan.set_defaults(func=cmd_scan)

    trim = sub.add_parser("trim", help="Lossless trim from reviewed CSV")
    trim.add_argument("csv", help="Review CSV from scan")
    trim.add_argument(
        "-o",
        "--output-dir",
        help="Output directory (default: same folder as source, *.trimmed.mp4)",
    )
    trim.add_argument("--dry-run", action="store_true", help="Show plan without ffmpeg")
    trim.set_defaults(func=cmd_trim)

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
