"""Detection presets (default vs DJI mostly-static camera)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DetectPreset:
    """Tunable freezedetect / downscale defaults for scan."""

    name: str
    noise_db: float
    min_duration: float
    scale_width: int | None
    sample_fps: float | None
    prefer_hwaccel: bool = True


# Strict pixel freeze (original freezedetect behaviour).
PRESET_DEFAULT = DetectPreset(
    name="default",
    noise_db=-60.0,
    min_duration=5.0,
    scale_width=None,
    sample_fps=None,
    prefer_hwaccel=False,
)

# Fast batch with moderate downscale (still fairly strict noise).
PRESET_FAST = DetectPreset(
    name="fast",
    noise_db=-60.0,
    min_duration=5.0,
    scale_width=480,
    sample_fps=3.0,
    prefer_hwaccel=True,
)

# DJI “camera died” with residual motion in part of the frame.
# Heavy downscale + loose noise catches mostly-static scenes.
PRESET_DJI = DetectPreset(
    name="dji",
    noise_db=-20.0,
    min_duration=5.0,
    scale_width=160,
    sample_fps=2.0,
    prefer_hwaccel=True,
)

PRESETS = {
    PRESET_DEFAULT.name: PRESET_DEFAULT,
    PRESET_FAST.name: PRESET_FAST,
    PRESET_DJI.name: PRESET_DJI,
}
