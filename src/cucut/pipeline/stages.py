"""Scan stage presets for the multi-pass pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScanStage:
    """One pipeline detection pass."""

    name: str
    min_duration: float
    noise_db: float = -60.0
    scale_width: int | None = None
    sample_fps: float | None = None
    region_pad_sec: float = 0.0
    """Fine stage: scan only padded windows around prior hits (0 = full file)."""


# Pass 1: very fast — long freezes only, low resolution.
STAGE_COARSE = ScanStage(
    name="coarse",
    min_duration=12.0,
    scale_width=320,
    sample_fps=2.0,
)

# Pass 2: medium — shorter freezes, more pixels/fps, candidate files only.
STAGE_MEDIUM = ScanStage(
    name="medium",
    min_duration=5.0,
    scale_width=480,
    sample_fps=5.0,
)

# Pass 3: fine — full timeline on candidates (or windows around prior hits).
STAGE_FINE = ScanStage(
    name="fine",
    min_duration=5.0,
    scale_width=960,
    sample_fps=10.0,
    region_pad_sec=8.0,
)

DEFAULT_PIPELINE = (STAGE_COARSE, STAGE_MEDIUM, STAGE_FINE)

# DJI mostly-static camera (loose noise + heavy downscale).
STAGE_COARSE_DJI = ScanStage(
    name="coarse",
    min_duration=8.0,
    noise_db=-20.0,
    scale_width=160,
    sample_fps=2.0,
)

STAGE_MEDIUM_DJI = ScanStage(
    name="medium",
    min_duration=5.0,
    noise_db=-20.0,
    scale_width=320,
    sample_fps=3.0,
)

STAGE_FINE_DJI = ScanStage(
    name="fine",
    min_duration=5.0,
    noise_db=-25.0,
    scale_width=480,
    sample_fps=5.0,
    region_pad_sec=8.0,
)

DJI_PIPELINE = (STAGE_COARSE_DJI, STAGE_MEDIUM_DJI, STAGE_FINE_DJI)
