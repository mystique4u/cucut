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
    with patch(
        "cucut.web.app.probe_video_info",
        return_value={
            "width": 3840,
            "height": 2160,
            "codec": "hevc",
            "duration": 12.0,
            "fps": 29.97,
            "res_label": "4K",
            "label": "4K 3840x2160 HEVC",
        },
    ):
        data = client.get("/api/browse", params={"dir": str(tmp_path)}).json()
    assert data["dir"] == str(tmp_path.resolve())
    types = {e["name"]: e["type"] for e in data["entries"]}
    assert types["clip.mp4"] == "file"
    assert types["sub"] == "dir"
    assert "note.txt" not in types
    clip = next(e for e in data["entries"] if e["name"] == "clip.mp4")
    assert clip["meta_label"] == "4K 3840x2160 HEVC"
    assert clip["res_label"] == "4K"
    assert clip["duration_label"] == "0:12"
    assert "thumb_url" in clip
    assert clip["thumb_url"].startswith("/api/thumb?")

    with patch("cucut.web.app.ensure_folder_thumb", return_value=str(tmp_path / "t.jpg")):
        (tmp_path / "t.jpg").write_bytes(b"jpeg")
        thumb = client.get("/api/thumb", params={"path": str(video)})
        assert thumb.status_code == 200
        assert thumb.content == b"jpeg"

    jobs = client.get("/api/jobs").json()
    assert "jobs" in jobs
    assert jobs["active"] == 0


def test_review_creates_missing_csv(tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")

    csv_path = tmp_path / "fresh.csv"
    assert not csv_path.exists()
    app = create_app(csv_path)
    assert csv_path.is_file()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    state = client.get("/api/state").json()
    assert state["segments"] == []
    assert state["videos"] == []
    assert Path(state["csv_path"]) == csv_path.resolve()


def test_scan_start_updates_csv(tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    csv_path = tmp_path / "segments.csv"
    write_segments(csv_path, [])
    app = create_app(csv_path)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    row = SegmentRow(
        path=str(video),
        seg_start=1.0,
        seg_end=6.0,
        duration=60.0,
        dead_sec=5.0,
        confidence="high",
        action="review",
        reviewed="no",
    )

    def _scan(root, output, **kwargs):
        write_segments(output, [row])
        on_file = kwargs.get("on_file")
        if on_file:
            on_file(video, 1, 1)
            on_file(video, 1, 1, 100.0)
        return [row], 1

    with patch("cucut.web.app.scan_directory", side_effect=_scan):
        started = client.post(
            "/api/scan/start",
            json={"dir": str(tmp_path), "mode": "dji", "output": str(csv_path)},
        )
        assert started.status_code == 200
        assert started.json()["ok"] is True

        import time

        status = {"status": "queued"}
        for _ in range(50):
            status = client.get("/api/scan/status").json()
            if status["status"] in {"ready", "error"}:
                break
            time.sleep(0.05)
        assert status["status"] == "ready", status
        assert status["segments"] == 1

        state = client.get("/api/state").json()
        assert len(state["segments"]) == 1
        assert state["videos"][0]["name"] == "clip.mp4"

        jobs = client.get("/api/jobs").json()
        kinds = {j["kind"] for j in jobs["jobs"]}
        assert "scan" in kinds

        cleared = client.post("/api/jobs/clear").json()
        assert cleared["ok"] is True
        assert cleared["removed"] >= 1
        assert client.get("/api/jobs").json()["jobs"] == []


def test_browse_roots_and_dirs_only(tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")

    (tmp_path / "sub").mkdir()
    (tmp_path / "clip.mp4").write_bytes(b"x")
    csv_path = tmp_path / "segments.csv"
    write_segments(csv_path, [])
    app = create_app(csv_path)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    roots = client.get("/api/browse/roots").json()
    assert roots["roots"]
    assert any(r["path"] for r in roots["roots"])

    data = client.get(
        "/api/browse",
        params={"dir": str(tmp_path), "dirs_only": True, "meta": False},
    ).json()
    names = {e["name"] for e in data["entries"]}
    assert "sub" in names
    assert "clip.mp4" not in names


def test_workspace_set_and_paths(tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")

    csv_path = tmp_path / "segments.csv"
    write_segments(csv_path, [])
    app = create_app(csv_path)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    state = client.get("/api/state").json()
    assert Path(state["workspace"]) == tmp_path.resolve()
    assert Path(state["tmp"]) == (tmp_path / ".cucut" / "tmp").resolve()
    assert Path(state["proxies"]) == (tmp_path / ".cucut" / "proxies").resolve()

    other = tmp_path / "ws2"
    set_res = client.post("/api/workspace", json={"path": str(other)})
    assert set_res.status_code == 200
    body = set_res.json()
    assert Path(body["workspace"]) == other.resolve()
    assert Path(body["csv_path"]) == (other / ".cucut" / "segments.csv").resolve()
    assert (other / ".cucut" / "tmp").is_dir()
    assert (other / ".cucut" / "proxies").is_dir()
    assert (other / ".cucut" / "segments.csv").is_file()


def test_jobs_lists_queued_cut(tmp_path, monkeypatch):
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
                duration=60.0,
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

    import threading

    gate = threading.Event()

    def _slow_cut(source, output, start, end, *, on_progress=None):
        gate.wait(timeout=2.0)
        if on_progress:
            on_progress(100.0)

    with (
        patch("cucut.web.app.lossless_remove_range", side_effect=_slow_cut),
        patch("cucut.web.app.remove_range_strategy", return_value="keep-head"),
    ):
        client.post(
            "/api/quickcut",
            json={"path": str(video), "start": 10.0, "end": 50.0},
        )
        jobs = client.get("/api/jobs").json()
        kinds = {j["kind"] for j in jobs["jobs"]}
        assert "cut" in kinds
        assert jobs["active"] >= 1
        gate.set()
