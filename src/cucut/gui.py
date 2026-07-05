"""Launch external GUI tools (LosslessCut, frame-checker)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


class GuiToolNotFoundError(RuntimeError):
    pass


def _find_executable(candidates: list[str]) -> str | None:
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
    return None


def find_losslesscut() -> str:
    path = _find_executable(
        [
            "losslesscut",
            "LosslessCut",
            "lossless-cut",
        ]
    )
    if path:
        return path

    # Flatpak / common install locations on Linux
    flatpak = shutil.which("flatpak")
    if flatpak:
        try:
            subprocess.run(
                ["flatpak", "info", "io.github.mifi.LosslessCut"],
                capture_output=True,
                check=True,
            )
            return "flatpak run io.github.mifi.LosslessCut"
        except subprocess.CalledProcessError:
            pass

    raise GuiToolNotFoundError(
        "LosslessCut not found. Install from https://github.com/mifi/lossless-cut "
        "or use `cucut export` and import CSV manually."
    )


def find_frame_checker() -> str:
    path = _find_executable(["frame-checker", "frame_checker"])
    if path:
        return path

    # pip-installed module
    if shutil.which("python3"):
        try:
            subprocess.run(
                [sys.executable, "-m", "frame_checker.main", "--help"],
                capture_output=True,
                check=True,
            )
            return f"{sys.executable} -m frame_checker.main"
        except subprocess.CalledProcessError:
            pass

    raise GuiToolNotFoundError(
        "frame-checker not found. Install with: pip install frame-checker "
        "(https://github.com/kuvk/frame-checker)"
    )


def launch(tool: str, *, video: Path | None = None, csv: Path | None = None) -> int:
    if tool == "losslesscut":
        command = find_losslesscut()
    elif tool == "frame-checker":
        command = find_frame_checker()
    else:
        raise ValueError(f"unknown tool: {tool}")

    args: list[str]
    if " " in command and not Path(command.split()[0]).exists():
        # flatpak-style compound command
        args = command.split()
    else:
        args = [command]

    if tool == "losslesscut":
        if video:
            args.append(str(video))
        env = os.environ.copy()
        if csv:
            env["CUCUT_LOSSLESSCUT_CSV"] = str(csv.resolve())
        proc = subprocess.Popen(args, env=env)
    else:
        proc = subprocess.Popen(args)

    return proc.wait()
