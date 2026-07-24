from pathlib import Path

from cucut.csvio import SegmentRow
from cucut.pipeline.regions import windows_from_rows
from cucut.pipeline.runner import _unique_paths
from cucut.pipeline.stages import STAGE_COARSE, STAGE_FINE, STAGE_MEDIUM
from cucut.segments import Interval


def test_windows_from_rows_merges_with_pad():
    rows = [
        SegmentRow(
            path="/tmp/a.mp4",
            seg_start=100.0,
            seg_end=120.0,
            duration=300.0,
            dead_sec=20.0,
            confidence="high",
            action="remove",
            reviewed="no",
        ),
        SegmentRow(
            path="/tmp/a.mp4",
            seg_start=125.0,
            seg_end=130.0,
            duration=300.0,
            dead_sec=5.0,
            confidence="medium",
            action="remove",
            reviewed="no",
        ),
    ]
    windows = windows_from_rows(rows, 300.0, pad_sec=8.0)
    assert len(windows) == 1
    assert windows[0].start == 92.0
    assert windows[0].end == 138.0


def test_windows_from_rows_empty():
    windows = windows_from_rows([], 60.0, pad_sec=5.0)
    assert windows == [Interval(0.0, 60.0)]


def test_unique_paths():
    rows = [
        SegmentRow(
            path="/a/x.mp4",
            seg_start=0,
            seg_end=10,
            duration=100,
            dead_sec=10,
            confidence="high",
            action="remove",
            reviewed="no",
        ),
        SegmentRow(
            path="/a/x.mp4",
            seg_start=20,
            seg_end=30,
            duration=100,
            dead_sec=10,
            confidence="high",
            action="remove",
            reviewed="no",
        ),
        SegmentRow(
            path="/b/y.mp4",
            seg_start=0,
            seg_end=5,
            duration=50,
            dead_sec=5,
            confidence="medium",
            action="remove",
            reviewed="no",
        ),
    ]
    paths = _unique_paths(rows)
    assert paths == [Path("/a/x.mp4"), Path("/b/y.mp4")]


def test_stage_presets():
    assert STAGE_COARSE.min_duration >= STAGE_MEDIUM.min_duration
    assert STAGE_FINE.region_pad_sec > 0


def test_probe_duration_unreadable(tmp_path):
    from cucut.ffmpeg import VideoUnreadableError, probe_duration

    bad = tmp_path / "broken.mp4"
    bad.write_bytes(b"not a real mp4")
    try:
        probe_duration(str(bad))
        raise AssertionError("expected VideoUnreadableError")
    except VideoUnreadableError as exc:
        assert "broken.mp4" in str(exc)


def test_close_open_freeze_at_eof():
    from cucut.ffmpeg import close_open_freeze
    from cucut.segments import Interval

    closed = close_open_freeze(
        [],
        10.0,
        time_offset=770.0,
        last_time=100.0,
        file_end=1859.0,
        to=None,
    )
    assert closed == [Interval(780.0, 1859.0)]


def test_close_open_freeze_noop_when_closed():
    from cucut.ffmpeg import close_open_freeze

    assert close_open_freeze([], None, time_offset=0, last_time=10, file_end=10, to=None) == []


def test_dji_preset():
    from cucut.presets import PRESET_DJI

    assert PRESET_DJI.noise_db == -20.0
    assert PRESET_DJI.scale_width == 160
