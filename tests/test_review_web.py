from pathlib import Path
from unittest.mock import patch

from cucut.csvio import SegmentRow, write_segments
from cucut.web.app import create_app


def test_review_app_lists_and_patches(tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    csv_path = tmp_path / "segments.csv"
    write_segments(
        csv_path,
        [
            SegmentRow(
                path=str(video),
                seg_start=10.0,
                seg_end=20.0,
                duration=100.0,
                dead_sec=10.0,
                confidence="high",
                action="review",
                reviewed="no",
            )
        ],
    )

    app = create_app(csv_path)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    state = client.get("/api/state").json()
    assert len(state["videos"]) == 1
    assert state["videos"][0]["name"] == "clip.mp4"
    assert state["segments"][0]["action"] == "review"

    patched = client.patch("/api/segments/0", json={"action": "remove"}).json()
    assert patched["segment"]["action"] == "remove"
    assert patched["segment"]["reviewed"] == "yes"

    from cucut.csvio import read_segments

    rows = read_segments(csv_path)
    assert rows[0].action == "remove"
    assert rows[0].reviewed == "yes"


def test_quickcut_validates_and_cuts(tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    csv_path = tmp_path / "segments.csv"
    write_segments(
        csv_path,
        [
            SegmentRow(
                path=str(video),
                seg_start=0.0,
                seg_end=5.0,
                duration=60.0,
                dead_sec=5.0,
                confidence="high",
                action="remove",
                reviewed="no",
            )
        ],
    )
    app = create_app(csv_path)
    from fastapi.testclient import TestClient

    client = TestClient(app)

    bad = client.post(
        "/api/quickcut",
        json={"path": str(video), "start": 10.0, "end": 5.0},
    )
    assert bad.status_code == 400

    foreign = client.post(
        "/api/quickcut",
        json={"path": str(tmp_path / "other.txt"), "start": 0.0, "end": 1.0},
    )
    assert foreign.status_code in {403, 404}

    with (
        patch("cucut.web.app.lossless_remove_range") as cut,
        patch(
            "cucut.web.app.remove_range_strategy",
            return_value="keep-head",
        ),
    ):
        ok = client.post(
            "/api/quickcut",
            json={"path": str(video), "start": 733.0, "end": 791.0},
        )
        assert ok.status_code == 200
        body = ok.json()
        assert body["ok"] is True
        assert body["mode"] == "delete"
        assert body["output"].endswith("clip.cut.mp4")
        assert "/run/media/optimus/info/" not in body["output"]
        assert body["status"] in {"queued", "running", "ready"}

        import time

        status = {"status": "idle"}
        for _ in range(50):
            status = client.get("/api/quickcut/status", params={"path": str(video)}).json()
            if status["status"] in {"ready", "error"}:
                break
            time.sleep(0.05)
        assert status["status"] == "ready", status
        assert status["output"].endswith("clip.cut.mp4")
        cut.assert_called_once()
        args = cut.call_args[0]
        assert args[0] == str(video)
        assert args[2] == 733.0
        assert args[3] == 791.0
        assert Path(args[1]).parent == video.parent


def test_filmstrip_status_and_build(tmp_path, monkeypatch):
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")

    proxy_dir = tmp_path / "proxies"
    proxy_dir.mkdir()
    monkeypatch.setenv("CUCUT_PROXY_DIR", str(proxy_dir))

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    csv_path = tmp_path / "segments.csv"
    write_segments(
        csv_path,
        [
            SegmentRow(
                path=str(video),
                seg_start=0.0,
                seg_end=1.0,
                duration=10.0,
                dead_sec=1.0,
                confidence="high",
                action="review",
                reviewed="no",
            )
        ],
    )
    app = create_app(csv_path)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    st = client.get("/api/filmstrip/status", params={"path": str(video)}).json()
    assert st["status"] == "missing"

    with patch("cucut.web.app.ensure_filmstrip") as ensure:

        def _write_strip(source, *, interval=10.0, on_progress=None):
            from cucut.ffmpeg import filmstrip_dir_for

            out = Path(filmstrip_dir_for(source))
            out.mkdir(parents=True, exist_ok=True)
            (out / "00000_00.jpg").write_bytes(b"jpeg")
            meta = {
                "source": source,
                "duration": 10.0,
                "interval": 10.0,
                "frames": [{"t": 0.0, "file": "00000_00.jpg"}],
            }
            (out / "meta.json").write_text(__import__("json").dumps(meta), encoding="utf-8")
            if on_progress:
                on_progress(100.0)
            return meta

        ensure.side_effect = _write_strip
        built = client.post("/api/filmstrip/build", json={"path": str(video)})
        assert built.status_code == 200
        assert built.json()["status"] in {"building", "ready", "queued"}

        import time

        status = {"status": "missing"}
        for _ in range(50):
            status = client.get("/api/filmstrip/status", params={"path": str(video)}).json()
            if status["status"] == "ready":
                break
            time.sleep(0.05)
        assert status["status"] == "ready"
        meta = client.get("/api/filmstrip/meta", params={"path": str(video)})
        assert meta.status_code == 200
        body = meta.json()
        assert len(body["frames"]) == 1
        frame = client.get(
            "/api/filmstrip/frame",
            params={"path": str(video), "file": "00000_00.jpg"},
        )
        assert frame.status_code == 200


def test_preview_status_and_build(tmp_path, monkeypatch):
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")

    proxy_dir = tmp_path / "proxies"
    proxy_dir.mkdir()
    monkeypatch.setenv("CUCUT_PROXY_DIR", str(proxy_dir))

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    csv_path = tmp_path / "segments.csv"
    write_segments(
        csv_path,
        [
            SegmentRow(
                path=str(video),
                seg_start=0.0,
                seg_end=1.0,
                duration=10.0,
                dead_sec=1.0,
                confidence="high",
                action="review",
                reviewed="no",
            )
        ],
    )
    app = create_app(csv_path)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    st = client.get("/api/preview/status", params={"path": str(video)}).json()
    assert st["status"] == "missing"

    with patch("cucut.web.app.ensure_preview_proxy") as ensure:

        def _write_proxy(source, *, cache_dir=None, on_progress=None):
            from cucut.ffmpeg import proxy_path_for

            out = proxy_path_for(source, cache_dir=cache_dir)
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_bytes(b"proxy")
            if on_progress:
                on_progress(100.0)
            return out

        ensure.side_effect = _write_proxy
        built = client.post("/api/preview/build", json={"path": str(video)})
        assert built.status_code == 200
        assert built.json()["status"] in {"building", "ready", "queued"}

        # Wait briefly for background thread
        import time

        status = {"status": "missing"}
        for _ in range(50):
            status = client.get("/api/preview/status", params={"path": str(video)}).json()
            if status["status"] == "ready":
                break
            time.sleep(0.05)
        assert status["status"] == "ready"
        prev = client.get("/api/preview", params={"path": str(video)})
        assert prev.status_code == 200


def test_browse_lists_folder_videos(tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    (tmp_path / "sub").mkdir()
    (tmp_path / "note.txt").write_text("x")
    csv_path = tmp_path / "segments.csv"
    write_segments(
        csv_path,
        [
            SegmentRow(
                path=str(video),
                seg_start=0.0,
                seg_end=1.0,
                duration=10.0,
                dead_sec=1.0,
                confidence="high",
                action="review",
                reviewed="no",
            )
        ],
    )
    app = create_app(csv_path)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    data = client.get("/api/browse", params={"dir": str(tmp_path)}).json()
    assert data["dir"] == str(tmp_path.resolve())
    types = {e["name"]: e["type"] for e in data["entries"]}
    assert types["clip.mp4"] == "file"
    assert types["sub"] == "dir"
    assert "note.txt" not in types
