"""Local web UI for reviewing scan CSV before trim."""

from __future__ import annotations

import mimetypes
import os
import threading
from pathlib import Path

from cucut.csvio import ACTIONS, SegmentRow, group_by_path, read_segments, write_segments
from cucut.ffmpeg import (
    ScanCancelled,
    VideoUnreadableError,
    cucut_tmp_dir,
    ensure_filmstrip,
    ensure_folder_thumb,
    ensure_preview_proxy,
    filmstrip_dir_for,
    lossless_remove_range,
    probe_video_info,
    proxy_path_for,
    remove_range_strategy,
)
from cucut.presets import PRESETS
from cucut.scan import scan_directory

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


class ScanStartRequest(BaseModel):
    dir: str
    mode: str = "dji"
    output: str | None = None
    recursive: bool = True


class WorkspaceRequest(BaseModel):
    path: str


WEB_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(WEB_DIR / "templates"))
STATIC_DIR = WEB_DIR / "static"
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv"}
_FINISHED_JOB_STATUSES = frozenset({"ready", "error"})


def default_workspace() -> Path:
    """Prefer CUCUT_WORKSPACE, then FAST mount, then cwd."""
    for base in (
        os.environ.get("CUCUT_WORKSPACE"),
        "/mnt/FAST/cucut-workspace",
        None,
    ):
        root = Path(base) if base else Path.cwd() / "cucut-workspace"
        try:
            root.mkdir(parents=True, exist_ok=True)
            if os.access(root, os.W_OK):
                return root.resolve()
        except OSError:
            continue
    return (Path.cwd() / "cucut-workspace").resolve()


def workspace_store(workspace: Path) -> Path:
    """Artifact dir inside a video workspace (CSV / tmp / proxies)."""
    return (workspace / ".cucut").resolve()


def apply_workspace(root: Path) -> Path:
    """Create workspace layout and point tmp/proxy env vars at it."""
    workspace = root.expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    store = workspace_store(workspace)
    tmp = store / "tmp"
    proxies = store / "proxies"
    store.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    proxies.mkdir(parents=True, exist_ok=True)
    if not os.access(workspace, os.W_OK):
        raise OSError(f"Workspace not writable: {workspace}")

    # Prefer legacy flat CSV if present; else use .cucut/segments.csv.
    legacy_csv = workspace / "segments.csv"
    csv_path = legacy_csv if legacy_csv.is_file() else store / "segments.csv"

    os.environ["CUCUT_WORKSPACE"] = str(workspace)
    os.environ["CUCUT_TMPDIR"] = str(tmp)
    os.environ["CUCUT_TMP"] = str(tmp)
    os.environ["CUCUT_PROXY_DIR"] = str(proxies)
    os.environ["TMPDIR"] = str(tmp)
    os.environ["TEMP"] = str(tmp)
    os.environ["TMP"] = str(tmp)

    marker = store / "workspace"
    try:
        marker.write_text(f"{workspace}\n", encoding="utf-8")
    except OSError:
        pass
    # Stash resolved CSV path for helpers that only know the workspace root.
    os.environ["CUCUT_REVIEW_CSV"] = str(csv_path.resolve())
    return workspace


def workspace_csv(workspace: Path) -> Path:
    legacy = (workspace / "segments.csv").resolve()
    if legacy.is_file():
        return legacy
    env_csv = os.environ.get("CUCUT_REVIEW_CSV")
    if env_csv:
        path = Path(env_csv)
        if path.parent == workspace or path.parent == workspace_store(workspace):
            return path.resolve()
    return (workspace_store(workspace) / "segments.csv").resolve()


def default_review_csv() -> Path:
    """Default CSV lives in the active workspace."""
    return workspace_csv(default_workspace())


def ensure_review_csv(csv_path: Path | None) -> Path:
    """Resolve CSV path; create an empty review CSV if missing."""
    path = (csv_path or default_review_csv()).expanduser().resolve()
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_segments(path, [])
    return path


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


def _format_duration_short(seconds: float) -> str:
    total = int(max(0.0, seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


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

    def list_jobs(self) -> list[dict[str, object]]:
        with self._lock:
            return [
                {
                    "path": path,
                    "status": job.get("status"),
                    "progress": job.get("progress", 0.0),
                    "error": job.get("error"),
                }
                for path, job in self._jobs.items()
            ]

    def clear_finished(self) -> int:
        with self._lock:
            remove = [
                path
                for path, job in self._jobs.items()
                if job.get("status") in _FINISHED_JOB_STATUSES
            ]
            for path in remove:
                del self._jobs[path]
            return len(remove)

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

    def list_jobs(self) -> list[dict[str, object]]:
        with self._lock:
            out: list[dict[str, object]] = []
            for path, job in self._jobs.items():
                row = dict(job)
                row["path"] = path
                out.append(row)
            return out

    def clear_finished(self) -> int:
        with self._lock:
            remove = [
                path
                for path, job in self._jobs.items()
                if job.get("status") in _FINISHED_JOB_STATUSES
            ]
            for path in remove:
                del self._jobs[path]
            return len(remove)

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


class _ScanJobs:
    """Single background freezedetect scan (one at a time)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._job: dict[str, object] | None = None
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._proc: object | None = None

    def status(self) -> dict[str, object]:
        with self._lock:
            if not self._job:
                return {
                    "status": "idle",
                    "progress": 0.0,
                    "path": "",
                    "name": "",
                    "error": None,
                    "file": None,
                    "file_index": 0,
                    "file_total": 0,
                    "mode": None,
                    "output": None,
                    "segments": 0,
                }
            return dict(self._job)

    def list_jobs(self) -> list[dict[str, object]]:
        info = self.status()
        if info["status"] == "idle":
            return []
        return [info]

    def clear_finished(self) -> int:
        with self._lock:
            if self._job and self._job.get("status") in _FINISHED_JOB_STATUSES | {"cancelled"}:
                self._job = None
                return 1
            return 0

    def cancel(self) -> dict[str, object]:
        """Request cancel; kills the active freezedetect ffmpeg if any."""
        with self._lock:
            if not self._job or self._job.get("status") not in {"queued", "running"}:
                return (
                    self.status()
                    if self._job
                    else {
                        "status": "idle",
                        "progress": 0.0,
                    }
                )
            self._cancel.set()
            self._job["status"] = "cancelling"
            proc = self._proc
        if proc is not None:
            try:
                proc.kill()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
        return self.status()

    def start(
        self,
        directory: Path,
        output: Path,
        *,
        mode: str,
        recursive: bool,
        on_done: object,
    ) -> dict[str, object]:
        with self._lock:
            if self._job and self._job.get("status") in {
                "queued",
                "running",
                "cancelling",
            }:
                raise HTTPException(status_code=409, detail="Scan already running")
            self._cancel.clear()
            self._proc = None
            self._job = {
                "status": "queued",
                "progress": 0.0,
                "path": str(directory),
                "name": directory.name or str(directory),
                "error": None,
                "file": None,
                "file_index": 0,
                "file_total": 0,
                "mode": mode,
                "output": str(output),
                "segments": 0,
            }

        def run() -> None:
            preset = PRESETS[mode]
            hwaccel = "auto" if preset.prefer_hwaccel else None

            def on_file(
                video: Path,
                index: int,
                total: int,
                pct: float | None = None,
            ) -> None:
                with self._lock:
                    assert self._job is not None
                    if self._job.get("status") != "cancelling":
                        self._job["status"] = "running"
                    self._job["file"] = video.name
                    self._job["file_index"] = index
                    self._job["file_total"] = total
                    if total <= 0:
                        self._job["progress"] = 0.0
                    elif pct is None:
                        self._job["progress"] = (index - 1) / total * 100.0
                    else:
                        self._job["progress"] = ((index - 1) + pct / 100.0) / total * 100.0

            def on_proc(proc: object | None) -> None:
                with self._lock:
                    self._proc = proc

            try:
                with self._lock:
                    assert self._job is not None
                    self._job["status"] = "running"
                rows, _n = scan_directory(
                    directory,
                    output,
                    noise_db=preset.noise_db,
                    min_duration=preset.min_duration,
                    hwaccel=hwaccel,
                    scale_width=preset.scale_width,
                    sample_fps=preset.sample_fps,
                    recursive=recursive,
                    on_file=on_file,
                    should_cancel=self._cancel.is_set,
                    on_proc=on_proc,
                )
                if self._cancel.is_set():
                    raise ScanCancelled("scan cancelled")
                # on_done: Callable[[list[SegmentRow], Path], None]
                on_done(rows, output)  # type: ignore[operator]
                with self._lock:
                    assert self._job is not None
                    self._job.update(
                        {
                            "status": "ready",
                            "progress": 100.0,
                            "segments": len(rows),
                            "error": None,
                        }
                    )
            except ScanCancelled:
                with self._lock:
                    assert self._job is not None
                    self._job.update(
                        {
                            "status": "cancelled",
                            "error": "Cancelled",
                        }
                    )
            except Exception as exc:  # noqa: BLE001 — surface to UI
                with self._lock:
                    assert self._job is not None
                    if self._cancel.is_set():
                        self._job.update(
                            {
                                "status": "cancelled",
                                "error": "Cancelled",
                            }
                        )
                    else:
                        self._job.update(
                            {
                                "status": "error",
                                "error": str(exc)[:400],
                            }
                        )
            finally:
                with self._lock:
                    self._proc = None

        self._thread = threading.Thread(target=run, name="cucut-scan", daemon=True)
        self._thread.start()
        return self.status()


def create_app(
    csv_path: Path | None = None,
    *,
    workspace: Path | None = None,
) -> FastAPI:
    resolved_csv = Path(csv_path).expanduser().resolve() if csv_path else None
    if workspace is not None:
        workspace_root = apply_workspace(workspace)
    elif resolved_csv is not None:
        # CSV parent is the workspace (keeps tests + one-off CSVs self-contained).
        workspace_root = apply_workspace(resolved_csv.parent)
    elif os.environ.get("CUCUT_WORKSPACE"):
        workspace_root = apply_workspace(Path(os.environ["CUCUT_WORKSPACE"]))
    else:
        workspace_root = apply_workspace(default_workspace())

    if resolved_csv is None:
        resolved_csv = workspace_csv(workspace_root)
    resolved_csv = ensure_review_csv(resolved_csv)

    state: dict[str, object] = {
        "workspace": workspace_root,
        "csv_path": resolved_csv,
        "rows": read_segments(resolved_csv),
        "preview": _PreviewJobs(),
        "filmstrip": _FilmstripJobs(),
        "cuts": _CutJobs(),
        "scan": _ScanJobs(),
        "meta_cache": {},
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

    def scan_jobs() -> _ScanJobs:
        return state["scan"]  # type: ignore[return-value]

    def workspace_path() -> Path:
        return state["workspace"]  # type: ignore[return-value]

    def meta_cache() -> dict[str, dict[str, object]]:
        return state["meta_cache"]  # type: ignore[return-value]

    def workspace_info() -> dict[str, str]:
        root = workspace_path()
        store = workspace_store(root)
        return {
            "workspace": str(root),
            "workspace_name": root.name or str(root),
            "csv_path": str(state["csv_path"]),
            "tmp": str(store / "tmp"),
            "proxies": str(store / "proxies"),
        }

    def allowed_paths() -> set[str]:
        return {row.path for row in rows()}

    def default_browse_dir() -> str:
        return str(workspace_path())

    def video_meta_for(path: Path) -> dict[str, object]:
        cache = meta_cache()
        try:
            st = path.stat()
            key = f"{path}|{st.st_mtime_ns}|{st.st_size}"
        except OSError:
            return {"meta_label": ""}
        hit = cache.get(key)
        if hit is not None:
            return hit
        try:
            info = probe_video_info(str(path))
            entry: dict[str, object] = {
                "width": info["width"],
                "height": info["height"],
                "codec": info["codec"],
                "duration": info["duration"],
                "fps": info["fps"],
                "res_label": info["res_label"],
                "meta_label": info["label"],
            }
        except (VideoUnreadableError, OSError, ValueError):
            entry = {"meta_label": ""}
        # Drop stale keys for this path
        prefix = f"{path}|"
        for old in [k for k in cache if k.startswith(prefix) and k != key]:
            del cache[old]
        cache[key] = entry
        return entry

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
        info = workspace_info()
        return TEMPLATES.TemplateResponse(
            request,
            "review.html",
            {
                "csv_path": info["csv_path"],
                "workspace": info["workspace"],
                "videos": video_summaries(),
            },
        )

    @app.get("/api/state")
    async def api_state() -> JSONResponse:
        info = workspace_info()
        return JSONResponse(
            {
                "csv_path": info["csv_path"],
                "workspace": info["workspace"],
                "tmp": info["tmp"],
                "proxies": info["proxies"],
                "videos": video_summaries(),
                "segments": [_row_dict(r, i) for i, r in enumerate(rows())],
                "browse_dir": default_browse_dir(),
            }
        )

    @app.get("/api/workspace")
    async def api_workspace_get() -> JSONResponse:
        return JSONResponse(workspace_info())

    @app.post("/api/workspace")
    async def api_workspace_set(payload: WorkspaceRequest) -> JSONResponse:
        try:
            root = apply_workspace(Path(payload.path))
        except OSError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        csv = ensure_review_csv(workspace_csv(root))
        state["workspace"] = root
        state["csv_path"] = csv
        state["rows"] = read_segments(csv)
        return JSONResponse({"ok": True, **workspace_info(), "videos": video_summaries()})

    @app.get("/api/browse/roots")
    async def api_browse_roots() -> JSONResponse:
        """Quick jump targets for the folder picker."""
        candidates: list[tuple[str, Path]] = [
            ("Home", Path.home()),
            ("FAST", Path("/mnt/FAST")),
            ("Root", Path("/")),
            ("Workspace", workspace_path()),
        ]
        media = Path("/run/media")
        if media.is_dir():
            try:
                for child in sorted(media.iterdir()):
                    if child.is_dir():
                        candidates.append((child.name, child))
            except OSError:
                pass
        roots: list[dict[str, str]] = []
        seen: set[str] = set()
        for label, path in candidates:
            try:
                if not path.is_dir():
                    continue
                resolved = str(path.resolve())
                if resolved in seen:
                    continue
                seen.add(resolved)
                roots.append({"label": label, "path": resolved})
            except OSError:
                continue
        return JSONResponse({"roots": roots})

    @app.get("/api/browse")
    async def api_browse(
        dir: str | None = None,
        meta: bool = True,
        dirs_only: bool = False,
    ) -> JSONResponse:
        """List subfolders + video files in a directory (optional ffprobe metadata)."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        root = Path(dir or default_browse_dir()).expanduser().resolve()
        if not root.is_dir():
            raise HTTPException(status_code=404, detail=f"Not a directory: {root}")
        dirs: list[dict] = []
        files: list[dict] = []
        try:
            children = list(root.iterdir())
        except OSError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        skip_names = {".cucut", "tmp", "proxies", ".git", ".venv"}
        for child in children:
            try:
                if child.name in skip_names or child.name.startswith("."):
                    continue
                if child.is_dir():
                    dirs.append({"type": "dir", "name": child.name, "path": str(child)})
                elif not dirs_only and child.is_file() and child.suffix.lower() in VIDEO_SUFFIXES:
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
        if meta and files:
            from urllib.parse import quote

            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(video_meta_for, Path(f["path"])): f for f in files}
                for fut in as_completed(futures):
                    entry = futures[fut]
                    try:
                        info = fut.result()
                    except Exception:  # noqa: BLE001
                        info = {"meta_label": ""}
                    duration = float(info.get("duration") or 0.0)
                    entry["width"] = info.get("width")
                    entry["height"] = info.get("height")
                    entry["codec"] = info.get("codec")
                    entry["duration"] = duration
                    entry["duration_label"] = (
                        _format_duration_short(duration) if duration > 0 else ""
                    )
                    entry["fps"] = info.get("fps")
                    entry["res_label"] = info.get("res_label")
                    entry["meta_label"] = info.get("meta_label") or ""
                    entry["thumb_url"] = f"/api/thumb?path={quote(str(entry['path']))}"
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

    @app.get("/api/thumb")
    async def api_thumb(path: str) -> FileResponse:
        """Cheap single-frame JPEG for Folder sidebar (cached under .cucut/proxies/thumbs)."""
        file_path = require_allowed_file(path)
        try:
            thumb = ensure_folder_thumb(str(file_path))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc
        return FileResponse(thumb, media_type="image/jpeg", filename=Path(thumb).name)

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

    @app.post("/api/scan/start")
    async def api_scan_start(payload: ScanStartRequest) -> JSONResponse:
        mode = payload.mode.strip().lower()
        if mode not in PRESETS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mode (choose {', '.join(sorted(PRESETS))})",
            )
        directory = Path(payload.dir).expanduser().resolve()
        if not directory.is_dir():
            raise HTTPException(status_code=404, detail=f"Not a directory: {directory}")
        # Always write scan CSV into the active workspace.
        if payload.output:
            requested = Path(payload.output).expanduser().resolve()
            if requested.parent == workspace_path() or requested == workspace_csv(workspace_path()):
                output = requested
            else:
                output = workspace_path() / requested.name
        else:
            output = workspace_csv(workspace_path())
        output = ensure_review_csv(output)

        def on_done(new_rows: list[SegmentRow], out: Path) -> None:
            state["csv_path"] = out
            state["rows"] = list(new_rows)

        info = scan_jobs().start(
            directory,
            output,
            mode=mode,
            recursive=payload.recursive,
            on_done=on_done,
        )
        return JSONResponse(
            {
                "ok": True,
                "status": info.get("status"),
                "progress": info.get("progress", 0.0),
                "dir": str(directory),
                "output": str(output),
                "mode": mode,
                "workspace": str(workspace_path()),
            }
        )

    @app.get("/api/scan/status")
    async def api_scan_status() -> JSONResponse:
        info = scan_jobs().status()
        return JSONResponse(info)

    @app.post("/api/scan/cancel")
    async def api_scan_cancel() -> JSONResponse:
        info = scan_jobs().cancel()
        return JSONResponse({"ok": True, **info})

    @app.get("/api/jobs")
    async def api_jobs() -> JSONResponse:
        """Snapshot of filmstrip / proxy / cut / scan background jobs."""
        jobs: list[dict[str, object]] = []
        for kind, manager in (
            ("filmstrip", filmstrip_jobs()),
            ("proxy", preview_jobs()),
            ("cut", cut_jobs()),
            ("scan", scan_jobs()),
        ):
            for job in manager.list_jobs():
                path = str(job.get("path") or "")
                name = str(job.get("name") or "") or (Path(path).name if path else "?")
                meta_bits = []
                if job.get("file") and job.get("file_total"):
                    meta_bits.append(
                        f"{job.get('file')} ({job.get('file_index')}/{job.get('file_total')})"
                    )
                jobs.append(
                    {
                        "kind": kind,
                        "path": path,
                        "name": name,
                        "status": job.get("status"),
                        "progress": float(job.get("progress") or 0.0),
                        "error": job.get("error"),
                        "strategy": job.get("strategy") or job.get("mode"),
                        "output": job.get("output"),
                        "detail": " · ".join(meta_bits) if meta_bits else None,
                    }
                )
        active = {"queued", "building", "running", "cancelling"}
        jobs.sort(
            key=lambda j: (
                0 if j["status"] in active else 1 if j["status"] == "error" else 2,
                str(j.get("name") or ""),
            )
        )
        return JSONResponse(
            {
                "jobs": jobs,
                "active": sum(1 for j in jobs if j["status"] in active),
            }
        )

    @app.post("/api/jobs/clear")
    async def api_jobs_clear() -> JSONResponse:
        """Remove finished (ready/error) jobs from the sidebar history."""
        removed = (
            filmstrip_jobs().clear_finished()
            + preview_jobs().clear_finished()
            + cut_jobs().clear_finished()
            + scan_jobs().clear_finished()
        )
        return JSONResponse({"ok": True, "removed": removed})

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


def serve_review(
    csv_path: Path | None = None,
    *,
    workspace: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    """Start local review server (blocking). CSV optional — created empty if missing."""
    import uvicorn

    workspace_root = apply_workspace(workspace or default_workspace())
    scratch = cucut_tmp_dir()
    resolved = ensure_review_csv(csv_path or workspace_csv(workspace_root))
    app = create_app(resolved, workspace=workspace_root)
    print(f"cucut review → http://{host}:{port}")
    print(f"Workspace: {workspace_root}")
    print(f"CSV: {resolved}")
    print(f"Scratch/tmp: {scratch}")
    print(f"Proxies: {workspace_store(workspace_root) / 'proxies'}")
    print("Open a video folder in the UI (Open workspace), then Scan.")
    print("Accept = cut (action=remove), Reject = keep. Then: cucut trim <csv>")
    print("I / O = mark delete range · Delete range = lossless remove")
    print("Filmstrip = fast seek thumbs · optional continuous proxy · Open in VLC for HEVC")
    uvicorn.run(app, host=host, port=port, log_level="info")
