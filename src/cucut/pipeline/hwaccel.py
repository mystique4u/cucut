"""Hardware decode selection (CUDA / auto)."""

from __future__ import annotations

import shutil
import subprocess


def list_hwaccels() -> set[str]:
    if not shutil.which("ffmpeg"):
        return set()
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-hwaccels"],
        capture_output=True,
        text=True,
        check=False,
    )
    methods: set[str] = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if line and not line.startswith("Hardware"):
            methods.add(line)
    return methods


def has_nvidia_gpu() -> bool:
    if not shutil.which("nvidia-smi"):
        return False
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def resolve_hwaccel(*, prefer_gpu: bool = True) -> str | None:
    """Pick best hwaccel. Prefer ``auto`` (NVDEC); else cuda/vaapi."""
    available = list_hwaccels()
    if not prefer_gpu:
        return None
    # ``auto`` is valid even when omitted from ``ffmpeg -hwaccels``.
    if "auto" in available or "cuda" in available or "vaapi" in available:
        return "auto"
    return None
