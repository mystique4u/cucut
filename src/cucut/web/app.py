"""Local web UI for reviewing scan CSV before trim."""

from __future__ import annotations

import mimetypes
import threading
from pathlib import Path

from cucut.csvio import ACTIONS, SegmentRow, group_by_path, read_segments, write_segments
from cucut.ffmpeg import (
    cucut_tmp_dir,
    ensure_filmstrip,
    ensure_preview_proxy,
    filmstrip_dir_for,
    lossless_remove_range,
    proxy_path_for,
    remove_range_strategy,
)

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Web review requires optional deps. Install with: pip install 'cucut[web]'"
    ) from exc


class SegmentPatch(BaseModel):
    action: str = Field(..., min_length=1)


class PreviewBuildRequest(BaseModel):
    path: str


class QuickCutRequest(BaseModel):
    path: str
    start: float
    end: float


class OpenExternalRequest(BaseModel):
    path: str
    time: float = 0.0


WEB_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(WEB_DIR / "templates"))
STATIC_DIR = WEB_DIR / "static"
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv"}


def _format_sec(value: float) -> str:
    minutes, seconds = divmod(value, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{int(hours):d}:{int(minutes):02d}:{seconds:05.2f}"
    return f"{int(minutes):d}:{seconds:05.2f}"


def _format_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)}{unit}"
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{num}B"


class _JobQueue:
    """One background worker; builds keyed by path."""

    def __init__(self, name: str, runner: object) -> None:
        import queue

        self._name = name
        self._runner = runner  # Callable[[str, Callable], None]
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, object]] = {}
        self._queue: queue.Queue[str] = queue.Queue()
        self._worker = threading.Thread(
            target=self._worker_loop,
            name=name,
            daemon=True,
        )
        self._worker.start()

    def _ready_check(self, path: str) -> dict[str, object] | None:
        raise NotImplementedError

    def status(self, path: str) -> dict[str, object]:
        ready = self._ready_check(path)
        if ready:
            return ready
        with self._lock:
            job = self._jobs.get(path)
            if job:
                return {
                    "status": job["status"],
                    "progress": job.get("progress", 0.0),
                    "error": job.get("error"),
                }
        return {"status": "missing", "progress": 0.0}

    def start(self, path: str) -> dict[str, object]:
        current = self.status(path)
        if current["status"] == "ready":
            return current
        with self._lock:
            job = self._jobs.get(path)
            if job and job.get("status") == "error":
                del self._jobs[path]
                job = None
            if job and job["status"] in {"building", "queued"}:
                return {
                    "status": job["status"],
                    "progress": job.get("progress", 0.0),
                }
            self._jobs[path] = {"status": "queued", "progress": 0.0}
        self._queue.put(path)
        return {"status": "queued", "progress": 0.0}

    def _worker_loop(self) -> None:
        while True:
            path = self._queue.get()
            try:
                with self._lock:
                    job = self._jobs.get(path)
                    if not job or job.get("status") not in {"queued", "building"}:
                        continue
                    job["status"] = "building"
                    job["progress"] = 0.0
                self._run(path)
            finally:
                self._queue.task_done()

    def _run(self, path: str) -> None:
        def on_progress(pct: float) -> None:
            with self._lock:
                job = self._jobs.get(path)
                if job:
                    job["progress"] = pct

        try:
            self._runner(path, on_progress)  # type: ignore[operator]
            with self._lock:
                self._jobs[path] = {"status": "ready", "progress": 100.0}
        except Exception as exc:  # noqa: BLE001 — surface to UI
            with self._lock:
                self._jobs[path] = {
                    "status": "error",
                    "progress": 0.0,
                    "error": str(exc)[:400],
                }


class _PreviewJobs(_JobQueue):
    """Optional continuous H.264 proxy — one encode at a time."""

    def __init__(self) -> None:
        def run(path: str, on_progress: object) -> None:
            ensure_preview_proxy(path, on_progress=on_progress)  # type: ignore[arg-type]

        super().__init__("cucut-proxy-worker", run)

    def _ready_check(self, path: str) -> dict[str, object] | None:
        proxy = proxy_path_for(path)
        if Path(proxy).is_file() and Path(proxy).stat().st_size > 0:
            return {"status": "ready", "progress": 100.0, "proxy": proxy}
        return None

    def status(self, path: str) -> dict[str, object]:
        info = super().status(path)
        info["proxy"] = proxy_path_for(path)
        return info


class _FilmstripJobs(_JobQueue):
    """Sparse seek JPEG filmstrip — fast navigation without full decode."""

    def __init__(self) -> None:
        def run(path: str, on_progress: object) -> None:
            ensure_filmstrip(path, on_progress=on_progress)  # type: ignore[arg-type]

        super().__init__("cucut-filmstrip-worker", run)

    def _ready_check(self, path: str) -> dict[str, object] | None:
        import json

        meta_path = Path(filmstrip_dir_for(path)) / "meta.json"
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
            if meta.get("frames"):
                return {
                    "status": "ready",
                    "progress": 100.0,
                    "dir": str(meta_path.parent),
                }
        return None

    def status(self, path: str) -> dict[str, object]:
        info = super().status(path)
        info["dir"] = filmstrip_dir_for(path)
        return info


class _CutJobs:
    """Background lossless delete-range jobs with progress."""

    def __init__(self) -> None:
        import queue

        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, object]] = {}
        self._queue: queue.Queue[str] = queue.Queue()
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="cucut-cut-worker",
            daemon=True,
        )
        self._worker.start()

    def status(self, path: str) -> dict[str, object]:
        with self._lock:
            job = self._jobs.get(path)
            if not job:
                return {"status": "idle", "progress": 0.0}
            return dict(job)

    def start(
        self,
        path: str,
        start: float,
        end: float,
        output: str,
    ) -> dict[str, object]:
        try:
            strategy = remove_range_strategy(path, start, end)
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "progress": 0.0,
                "error": str(exc)[:400],
            }
        with self._lock:
            job = self._jobs.get(path)
            if job and job.get("status") in {"queued", "running"}:
                return dict(job)
            self._jobs[path] = {
                "status": "queued",
                "progress": 0.0,
                "start": start,
                "end": end,
                "output": output,
                "strategy": strategy,
            }
        self._queue.put(path)
        return self.status(path)

    def _worker_loop(self) -> None:
        while True:
            path = self._queue.get()
            try:
                with self._lock:
                    job = self._jobs.get(path)
                    if not job or job.get("status") != "queued":
                        continue
                    job["status"] = "running"
                    job["progress"] = 0.0
                    start = float(job["start"])  # type: ignore[arg-type]
                    end = float(job["end"])  # type: ignore[arg-type]
                    output = str(job["output"])
                    strategy = str(job.get("strategy") or "")
                self._run(path, start, end, output, strategy)
            finally:
                self._queue.task_done()

    def _run(
        self,
        path: str,
        start: float,
        end: float,
        output: str,
        strategy: str,
    ) -> None:
        def on_progress(pct: float) -> None:
            with self._lock:
                job = self._jobs.get(path)
                if job:
                    job["progress"] = pct

        try:
            lossless_remove_range(path, output, start, end, on_progress=on_progress)
            with self._lock:
                self._jobs[path] = {
                    "status": "ready",
                    "progress": 100.0,
                    "output": output,
                    "strategy": strategy,
                    "start": start,
                    "end": end,
                }
        except Exception as exc:  # noqa: BLE001 — surface to UI
            with self._lock:
                self._jobs[path] = {
                    "status": "error",
                    "progress": 0.0,
                    "output": output,
                    "strategy": strategy,
                    "error": str(exc)[:400],
                }


def create_app(csv_path: Path) -> FastAPI:
    csv_path = csv_path.expanduser().resolve()
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    state: dict[str, object] = {
        "csv_path": csv_path,
        "rows": read_segments(csv_path),
        "preview": _PreviewJobs(),
        "filmstrip": _FilmstripJobs(),
        "cuts": _CutJobs(),
    }

    app = FastAPI(title="cucut review", docs_url=None, redoc_url=None)
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    def rows() -> list[SegmentRow]:
        return state["rows"]  # type: ignore[return-value]

    def preview_jobs() -> _PreviewJobs:
        return state["preview"]  # type: ignore[return-value]

    def filmstrip_jobs() -> _FilmstripJobs:
        return state["filmstrip"]  # type: ignore[return-value]

    def cut_jobs() -> _CutJobs:
        return state["cuts"]  # type: ignore[return-value]

    def allowed_paths() -> set[str]:
        return {row.path for row in rows()}

    def default_browse_dir() -> str:
        paths = [Path(p) for p in allowed_paths()]
        if paths:
            return str(paths[0].parent)
        for candidate in (
            Path("/mnt/FAST/cucut-chunk15"),
            Path("/run/media/optimus/info/DJI_001"),
        ):
            if candidate.is_dir():
                return str(candidate)
        return str(Path.home())

    def require_allowed_file(path: str) -> Path:
        """CSV paths always OK; any existing local video file also OK (localhost review)."""
        file_path = Path(path).expanduser().resolve()
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="Video file missing")
        if str(file_path) in allowed_paths():
            return file_path
        if file_path.suffix.lower() in VIDEO_SUFFIXES:
            return file_path
        raise HTTPException(status_code=403, detail="Not a video file")

    def video_summaries() -> list[dict]:
        grouped = group_by_path(rows())
        items: list[dict] = []
        for path, segs in sorted(grouped.items()):
            pending = sum(1 for s in segs if s.action == "review" or s.reviewed == "no")
            remove_n = sum(1 for s in segs if s.action == "remove")
            keep_n = sum(1 for s in segs if s.action == "keep")
            dead = sum(s.dead_sec for s in segs if s.action == "remove")
            items.append(
                {
                    "path": path,
                    "name": Path(path).name,
                    "count": len(segs),
                    "pending": pending,
                    "remove": remove_n,
                    "keep": keep_n,
                    "dead_remove_sec": dead,
                    "duration": segs[0].duration if segs else 0.0,
                }
            )
        return items

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request,
            "review.html",
            {
                "csv_path": str(state["csv_path"]),
                "videos": video_summaries(),
            },
        )

    @app.get("/api/state")
    async def api_state() -> JSONResponse:
        return JSONResponse(
            {
                "csv_path": str(state["csv_path"]),
                "videos": video_summaries(),
                "segments": [_row_dict(r, i) for i, r in enumerate(rows())],
                "browse_dir": default_browse_dir(),
            }
        )

    @app.get("/api/browse")
    async def api_browse(dir: str | None = None) -> JSONResponse:
        """List subfolders + video files in a directory."""
        root = Path(dir or default_browse_dir()).expanduser().resolve()
        if not root.is_dir():
            raise HTTPException(status_code=404, detail=f"Not a directory: {root}")
        dirs: list[dict] = []
        files: list[dict] = []
        try:
            children = list(root.iterdir())
        except OSError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        for child in children:
            try:
                if child.is_dir():
                    dirs.append({"type": "dir", "name": child.name, "path": str(child)})
                elif child.is_file() and child.suffix.lower() in VIDEO_SUFFIXES:
                    size = child.stat().st_size
                    files.append(
                        {
                            "type": "file",
                            "name": child.name,
                            "path": str(child),
                            "size": size,
                            "size_label": _format_size(size),
                        }
                    )
            except OSError:
                continue
        dirs.sort(key=lambda e: e["name"].lower())
        files.sort(key=lambda e: e["size"], reverse=True)
        parent = root.parent
        return JSONResponse(
            {
                "dir": str(root),
                "parent": str(parent) if parent != root else None,
                "entries": dirs + files,
            }
        )

    @app.get("/api/video")
    async def api_video(path: str) -> FileResponse:
        file_path = require_allowed_file(path)
        media_type = mimetypes.guess_type(str(file_path))[0] or "video/mp4"
        return FileResponse(
            file_path,
            media_type=media_type,
            filename=file_path.name,
        )

    @app.get("/api/filmstrip/status")
    async def api_filmstrip_status(path: str) -> JSONResponse:
        require_allowed_file(path)
        info = filmstrip_jobs().status(path)
        return JSONResponse(
            {
                "path": path,
                "status": info["status"],
                "progress": info.get("progress", 0.0),
                "error": info.get("error"),
            }
        )

    @app.post("/api/filmstrip/build")
    async def api_filmstrip_build(payload: PreviewBuildRequest) -> JSONResponse:
        require_allowed_file(payload.path)
        info = filmstrip_jobs().start(payload.path)
        return JSONResponse(
            {
                "path": payload.path,
                "status": info["status"],
                "progress": info.get("progress", 0.0),
                "error": info.get("error"),
            }
        )

    @app.get("/api/filmstrip/meta")
    async def api_filmstrip_meta(path: str) -> JSONResponse:
        import json
        from urllib.parse import quote

        require_allowed_file(path)
        info = filmstrip_jobs().status(path)
        if info["status"] != "ready":
            raise HTTPException(
                status_code=404,
                detail=f"Filmstrip not ready ({info['status']})",
            )
        meta_path = Path(str(info["dir"])) / "meta.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        q = quote(path)
        frames = [
            {
                "t": f["t"],
                "file": f["file"],
                "url": f"/api/filmstrip/frame?path={q}&file={quote(str(f['file']))}",
            }
            for f in meta.get("frames", [])
        ]
        return JSONResponse(
            {
                "path": path,
                "duration": meta.get("duration"),
                "interval": meta.get("interval"),
                "frames": frames,
            }
        )

    @app.get("/api/filmstrip/frame")
    async def api_filmstrip_frame(path: str, file: str) -> FileResponse:
        require_allowed_file(path)
        name = Path(file).name
        if name != file or "/" in file or "\\" in file or ".." in file:
            raise HTTPException(status_code=400, detail="Invalid frame name")
        frame = Path(filmstrip_dir_for(path)) / name
        if not frame.is_file():
            raise HTTPException(status_code=404, detail="Frame not found")
        return FileResponse(frame, media_type="image/jpeg", filename=name)

    @app.get("/api/preview/status")
    async def api_preview_status(path: str) -> JSONResponse:
        require_allowed_file(path)
        info = preview_jobs().status(path)
        return JSONResponse(
            {
                "path": path,
                "status": info["status"],
                "progress": info.get("progress", 0.0),
                "error": info.get("error"),
            }
        )

    @app.post("/api/preview/build")
    async def api_preview_build(payload: PreviewBuildRequest) -> JSONResponse:
        require_allowed_file(payload.path)
        info = preview_jobs().start(payload.path)
        return JSONResponse(
            {
                "path": payload.path,
                "status": info["status"],
                "progress": info.get("progress", 0.0),
                "error": info.get("error"),
            }
        )

    @app.get("/api/preview")
    async def api_preview(path: str) -> FileResponse:
        require_allowed_file(path)
        info = preview_jobs().status(path)
        if info["status"] != "ready":
            raise HTTPException(
                status_code=404,
                detail=f"Preview not ready ({info['status']})",
            )
        proxy = Path(str(info["proxy"]))
        return FileResponse(
            proxy,
            media_type="video/mp4",
            filename=proxy.name,
        )

    @app.post("/api/quickcut")
    async def api_quickcut(payload: QuickCutRequest) -> JSONResponse:
        """Start a background lossless delete; poll /api/quickcut/status."""
        file_path = require_allowed_file(payload.path)
        if payload.end <= payload.start:
            raise HTTPException(
                status_code=400,
                detail="end must be greater than start",
            )
        # Always write next to the source (same disk) — do not divert to info/.
        out = file_path.with_name(f"{file_path.stem}.cut{file_path.suffix}")
        info = cut_jobs().start(
            str(file_path),
            payload.start,
            payload.end,
            str(out),
        )
        return JSONResponse(
            {
                "ok": True,
                "path": payload.path,
                "output": str(out),
                "start": payload.start,
                "end": payload.end,
                "mode": "delete",
                "status": info["status"],
                "progress": info.get("progress", 0.0),
                "strategy": info.get("strategy"),
                "error": info.get("error"),
            }
        )

    @app.get("/api/quickcut/status")
    async def api_quickcut_status(path: str) -> JSONResponse:
        require_allowed_file(path)
        info = cut_jobs().status(path)
        return JSONResponse(
            {
                "path": path,
                "status": info["status"],
                "progress": info.get("progress", 0.0),
                "output": info.get("output"),
                "strategy": info.get("strategy"),
                "error": info.get("error"),
            }
        )

    @app.post("/api/open-external")
    async def api_open_external(payload: OpenExternalRequest) -> JSONResponse:
        """Open source in mpv/vlc (fast HEVC seek) at the given timestamp."""
        import shutil
        import subprocess

        file_path = require_allowed_file(payload.path)
        t = max(0.0, float(payload.time))
        mpv = shutil.which("mpv")
        vlc = shutil.which("vlc")
        if mpv:
            cmd = [mpv, f"--start={t}", "--pause", str(file_path)]
            player = "mpv"
        elif vlc:
            # VLC --start-time is seconds
            cmd = [vlc, f"--start-time={int(t)}", "--play-and-pause", str(file_path)]
            player = "vlc"
        else:
            raise HTTPException(
                status_code=501,
                detail="No external player (install mpv or vlc)",
            )
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return JSONResponse({"ok": True, "player": player, "time": t})

    @app.patch("/api/segments/{index}")
    async def api_patch_segment(index: int, payload: SegmentPatch) -> JSONResponse:
        current = rows()
        if index < 0 or index >= len(current):
            raise HTTPException(status_code=404, detail="Segment index out of range")

        action = payload.action.strip().lower()
        if action not in ACTIONS:
            raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

        row = current[index]
        updated = SegmentRow(
            path=row.path,
            seg_start=row.seg_start,
            seg_end=row.seg_end,
            duration=row.duration,
            dead_sec=row.dead_sec,
            confidence=row.confidence,
            action=action,
            reviewed="yes",
        )
        current[index] = updated
        write_segments(state["csv_path"], current)  # type: ignore[arg-type]
        return JSONResponse({"ok": True, "segment": _row_dict(updated, index)})

    @app.post("/api/save")
    async def api_save() -> JSONResponse:
        write_segments(state["csv_path"], rows())  # type: ignore[arg-type]
        return JSONResponse({"ok": True, "csv_path": str(state["csv_path"])})

    @app.post("/api/reload")
    async def api_reload() -> JSONResponse:
        state["rows"] = read_segments(state["csv_path"])  # type: ignore[arg-type]
        return JSONResponse({"ok": True, "videos": video_summaries()})

    return app


def _row_dict(row: SegmentRow, index: int) -> dict:
    return {
        "index": index,
        "path": row.path,
        "name": Path(row.path).name,
        "seg_start": row.seg_start,
        "seg_end": row.seg_end,
        "seg_start_label": _format_sec(row.seg_start),
        "seg_end_label": _format_sec(row.seg_end),
        "duration": row.duration,
        "dead_sec": row.dead_sec,
        "confidence": row.confidence,
        "action": row.action,
        "reviewed": row.reviewed,
    }


def serve_review(csv_path: Path, *, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Start local review server (blocking)."""
    import os

    import uvicorn

    # Keep ffmpeg/tempfile scratch off the full root disk.
    scratch = cucut_tmp_dir()
    os.environ.setdefault("TMPDIR", scratch)
    os.environ.setdefault("TEMP", scratch)
    os.environ.setdefault("TMP", scratch)

    app = create_app(csv_path)
    print(f"cucut review → http://{host}:{port}")
    print(f"CSV: {csv_path.resolve()}")
    print(f"Scratch/tmp: {scratch}")
    print("Accept = cut (action=remove), Reject = keep. Then: cucut trim <csv>")
    print("I / O = mark delete range · Delete range = lossless remove")
    print("Filmstrip = fast seek thumbs · optional continuous proxy · Open in VLC for HEVC")
    uvicorn.run(app, host=host, port=port, log_level="info")
