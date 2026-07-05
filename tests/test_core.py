from cucut.csvio import SegmentRow, classify_confidence, read_segments, write_segments
from cucut.segments import Interval, invert_intervals, merge_overlapping


def test_merge_overlapping():
    merged = merge_overlapping(
        [Interval(0, 5), Interval(4, 10), Interval(20, 25)],
    )
    assert merged == [Interval(0, 10), Interval(20, 25)]


def test_invert_intervals():
    dead = [Interval(10, 20), Interval(30, 40)]
    keep = invert_intervals(dead, 50.0)
    assert keep == [Interval(0, 10), Interval(20, 30), Interval(40, 50)]


def test_classify_confidence():
    assert classify_confidence(15, 100, 3) == "high"
    assert classify_confidence(4, 100, 3) == "medium"
    assert classify_confidence(3, 100, 3) == "low"


def test_csv_roundtrip(tmp_path):
    rows = [
        SegmentRow(
            path="/tmp/a.mp4",
            seg_start=10.0,
            seg_end=20.0,
            duration=100.0,
            dead_sec=10.0,
            confidence="high",
            action="remove",
            reviewed="no",
        )
    ]
    path = tmp_path / "segments.csv"
    write_segments(path, rows)
    loaded = read_segments(path)
    assert len(loaded) == 1
    assert loaded[0].action == "remove"
    assert loaded[0].seg_start == 10.0
