(() => {
  const state = {
    segments: [],
    videos: [],
    currentPath: null,
    clip: null, // { start, end, index } while playing a segment window
    markIn: null,
    markOut: null,
    usingProxy: false,
    scrubTime: 0,
    filmstripFrames: [],
    filmstripDuration: 0,
    previewPoll: null,
    filmstripPoll: null,
    cutPoll: null,
    sidebarMode: "segments", // segments | folder
    browseDir: null,
    browseParent: null,
    browseEntries: [],
    csvPath: "",
    workspace: "",
  };

  const videoList = document.getElementById("video-list");
  const emptyMain = document.getElementById("empty-main");
  const workspace = document.getElementById("workspace");
  const player = document.getElementById("player");
  const stillWrap = document.getElementById("still-wrap");
  const still = document.getElementById("still");
  const stillTime = document.getElementById("still-time");
  const filmstripEl = document.getElementById("filmstrip");
  const timeline = document.getElementById("timeline");
  const segList = document.getElementById("seg-list");
  const currentName = document.getElementById("current-name");
  const previewBanner = document.getElementById("preview-banner");
  const previewLoader = document.getElementById("preview-loader");
  const loaderTitle = document.getElementById("loader-title");
  const loaderSub = document.getElementById("loader-sub");
  const loaderFill = document.getElementById("loader-fill");
  const loaderPct = document.getElementById("loader-pct");
  const markInLabel = document.getElementById("mark-in-label");
  const markOutLabel = document.getElementById("mark-out-label");
  const btnSaveCut = document.getElementById("btn-save-cut");
  const toast = document.getElementById("toast");
  const scanModeSelect = document.getElementById("scan-mode");
  const scanRecursive = document.getElementById("scan-recursive");
  const btnScanStart = document.getElementById("btn-scan-start");
  const scanHint = document.getElementById("scan-hint");
  const segmentsTools = document.getElementById("segments-tools");
  const csvPathEl = document.getElementById("csv-path");
  const workspaceNameEl = document.getElementById("workspace-name");
  const folderPicker = document.getElementById("folder-picker");
  const pickerTitle = document.getElementById("picker-title");
  const pickerRoots = document.getElementById("picker-roots");
  const pickerPath = document.getElementById("picker-path");
  const pickerList = document.getElementById("picker-list");
  const pickerUp = document.getElementById("picker-up");

  function pathUnderWorkspace(path) {
    if (!state.workspace || !path) return false;
    const root = state.workspace.replace(/\/+$/, "");
    const p = String(path).replace(/\/+$/, "");
    return p === root || p.startsWith(root + "/");
  }

  function updateScanButton() {
    const hasSegs = state.videos.length > 0;
    btnScanStart.textContent = hasSegs ? "Rescan" : "Scan";
    scanHint.textContent = hasSegs
      ? "Rescan this workspace · replaces Segments CSV"
      : "No scan yet — press Scan for this workspace";
  }

  const pickerState = {
    open: false,
    dir: "",
    parent: null,
    selected: null,
    onSelect: null,
    title: "Choose folder",
  };

  function fmt(sec) {
    const s = Math.max(0, sec);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const r = s % 60;
    if (h) return `${h}:${String(m).padStart(2, "0")}:${r.toFixed(2).padStart(5, "0")}`;
    return `${m}:${r.toFixed(2).padStart(5, "0")}`;
  }

  function showToast(msg, ok = true) {
    toast.textContent = msg;
    toast.classList.toggle("error", !ok);
    toast.classList.remove("hidden");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => toast.classList.add("hidden"), 6000);
  }

  async function loadPickerRoots() {
    const res = await fetch("/api/browse/roots");
    const data = await res.json().catch(() => ({}));
    pickerRoots.innerHTML = "";
    for (const root of data.roots || []) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "picker-root";
      btn.textContent = root.label;
      btn.title = root.path;
      btn.addEventListener("click", () => loadPickerDir(root.path));
      pickerRoots.appendChild(btn);
    }
  }

  function renderPickerList(entries) {
    pickerList.innerHTML = "";
    const dirs = (entries || []).filter((e) => e.type === "dir");
    if (!dirs.length) {
      pickerList.innerHTML = '<li class="picker-empty">No subfolders here</li>';
      return;
    }
    for (const e of dirs) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className =
        "picker-item" + (pickerState.selected === e.path ? " selected" : "");
      btn.innerHTML = `<span class="picker-name">${escapeHtml(e.name)}/</span>`;
      btn.addEventListener("click", () => {
        pickerState.selected = e.path;
        renderPickerList(entries);
      });
      btn.addEventListener("dblclick", () => loadPickerDir(e.path));
      li.appendChild(btn);
      pickerList.appendChild(li);
    }
  }

  async function loadPickerDir(dir) {
    const q = new URLSearchParams({
      meta: "false",
      dirs_only: "true",
    });
    if (dir) q.set("dir", dir);
    const res = await fetch(`/api/browse?${q}`);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showToast(data.detail || "Browse failed", false);
      return;
    }
    pickerState.dir = data.dir;
    pickerState.parent = data.parent;
    pickerState.selected = data.dir;
    pickerPath.value = data.dir;
    pickerUp.disabled = !data.parent;
    renderPickerList(data.entries || []);
    for (const btn of pickerRoots.querySelectorAll(".picker-root")) {
      btn.classList.toggle("active", btn.title === data.dir);
    }
  }

  function closeFolderPicker() {
    pickerState.open = false;
    pickerState.onSelect = null;
    folderPicker.classList.add("hidden");
  }

  async function openFolderPicker({ title, startDir, onSelect }) {
    pickerState.open = true;
    pickerState.onSelect = onSelect;
    pickerState.title = title || "Choose folder";
    pickerTitle.textContent = pickerState.title;
    folderPicker.classList.remove("hidden");
    await loadPickerRoots();
    await loadPickerDir(startDir || state.workspace || state.browseDir || "");
    pickerPath.focus();
  }

  function confirmFolderPicker() {
    const path = pickerState.selected || pickerState.dir || pickerPath.value.trim();
    if (!path) {
      showToast("Pick a folder first", false);
      return;
    }
    const cb = pickerState.onSelect;
    closeFolderPicker();
    if (cb) cb(path);
  }

  let lastSegmentsSig = "";

  function segmentsSig(segments, videos) {
    return JSON.stringify({
      videos: (videos || []).map((v) => [v.path, v.count, v.remove, v.keep, v.pending]),
      segs: (segments || []).map((s) => [s.index, s.action, s.reviewed, s.path]),
    });
  }

  async function loadState() {
    const res = await fetch("/api/state");
    const data = await res.json();
    const sig = segmentsSig(data.segments, data.videos);
    const changed = sig !== lastSegmentsSig;
    lastSegmentsSig = sig;
    state.segments = data.segments;
    state.videos = data.videos;
    state.csvPath = data.csv_path || "";
    state.workspace = data.workspace || "";
    if (csvPathEl && state.csvPath) {
      csvPathEl.textContent = `CSV: ${state.csvPath}`;
      csvPathEl.title = state.csvPath;
    }
    if (workspaceNameEl && state.workspace) {
      workspaceNameEl.textContent = state.workspace;
      workspaceNameEl.title = state.workspace;
    }
    if (!state.browseDir || !pathUnderWorkspace(state.browseDir)) {
      state.browseDir = state.workspace || data.browse_dir || null;
    }
    updateScanButton();
    if (changed || state.sidebarMode === "folder") {
      renderSidebar();
    }
    if (changed && state.currentPath && state.sidebarMode === "segments") {
      selectVideo(state.currentPath);
    } else if (state.currentPath && changed) {
      renderSegments();
      renderTimeline();
    }
  }

  function setSidebarMode(mode) {
    state.sidebarMode = mode;
    document.getElementById("tab-segments").classList.toggle("active", mode === "segments");
    document.getElementById("tab-folder").classList.toggle("active", mode === "folder");
    segmentsTools.classList.toggle("hidden", mode !== "segments");
    renderSidebar();
    if (mode === "folder") loadFolder(state.workspace);
    if (mode === "segments") refreshSegments();
  }

  async function refreshSegments({ reread = true } = {}) {
    try {
      if (reread) {
        const res = await fetch("/api/reload", { method: "POST" });
        if (!res.ok) return;
      }
      await loadState();
    } catch {
      /* ignore */
    }
  }

  async function loadFolder(dir) {
    const root = state.workspace;
    let target = dir || root;
    if (root && target && !pathUnderWorkspace(target)) {
      target = root;
    }
    const q = new URLSearchParams();
    if (target) q.set("dir", target);
    const res = await fetch(`/api/browse?${q}`);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showToast(data.detail || "Browse failed", false);
      return;
    }
    state.browseDir = data.dir;
    const parent = data.parent;
    state.browseParent =
      parent && root && pathUnderWorkspace(parent) && parent !== root ? parent : null;
    // Allow Up to workspace root when inside a subfolder
    if (parent && root && parent === root && data.dir !== root) {
      state.browseParent = root;
    } else if (data.dir === root) {
      state.browseParent = null;
    } else if (parent && pathUnderWorkspace(parent)) {
      state.browseParent = parent;
    }
    state.browseEntries = data.entries || [];
    if (state.sidebarMode === "folder") renderSidebar();
  }

  function renderSidebar() {
    if (state.sidebarMode === "folder") {
      renderFolderList();
    } else {
      renderVideoList();
    }
  }

  function renderFolderList() {
    videoList.innerHTML = "";
    const up = state.browseParent;
    if (up) {
      const liUp = document.createElement("li");
      const btnUp = document.createElement("button");
      btnUp.type = "button";
      btnUp.className = "video-item dir";
      btnUp.innerHTML =
        `<span class="video-name">../</span>` +
        `<span class="video-meta">up</span>`;
      btnUp.addEventListener("click", () => loadFolder(up));
      liUp.appendChild(btnUp);
      videoList.appendChild(liUp);
    }
    if (!state.browseEntries.length) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = "No videos in this workspace folder";
      videoList.appendChild(li);
      return;
    }
    for (const e of state.browseEntries) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      const isActive = e.type === "file" && e.path === state.currentPath;
      btn.className =
        "video-item" + (e.type === "dir" ? " dir" : "") + (isActive ? " active" : "");
      if (e.type === "dir") {
        btn.innerHTML =
          `<span class="video-name">${escapeHtml(e.name)}/</span>` +
          `<span class="video-meta">folder</span>`;
        btn.addEventListener("click", () => loadFolder(e.path));
      } else {
        const inCsv = state.videos.some((v) => v.path === e.path);
        const bits = [];
        if (e.res_label) bits.push(e.res_label);
        else if (e.meta_label) bits.push(String(e.meta_label).split(" ")[0]);
        if (e.duration_label) bits.push(e.duration_label);
        if (e.codec) bits.push(String(e.codec).toUpperCase());
        if (e.size_label) bits.push(e.size_label);
        if (inCsv) bits.push("scanned");
        const thumb = e.thumb_url
          ? `<img class="video-thumb" src="${escapeHtml(e.thumb_url)}" alt="" loading="lazy" />`
          : `<span class="video-thumb placeholder" aria-hidden="true"></span>`;
        btn.className += " with-thumb";
        btn.innerHTML =
          thumb +
          `<span class="video-text">` +
          `<span class="video-name">${escapeHtml(e.name)}</span>` +
          `<span class="video-meta">${escapeHtml(bits.join(" · "))}</span>` +
          `</span>`;
        btn.addEventListener("click", () => selectVideo(e.path));
      }
      li.appendChild(btn);
      videoList.appendChild(li);
    }
  }

  function renderVideoList() {
    videoList.innerHTML = "";
    if (!state.videos.length) {
      videoList.innerHTML = '<li class="empty">No segments yet — press Scan</li>';
      return;
    }
    for (const v of state.videos) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "video-item" + (v.path === state.currentPath ? " active" : "");
      btn.dataset.path = v.path;
      btn.innerHTML =
        `<span class="video-name">${escapeHtml(v.name)}</span>` +
        `<span class="video-meta">${v.count} seg · ${v.remove} cut · ${v.keep} keep` +
        (v.pending ? ` · ${v.pending} open` : "") +
        `</span>`;
      btn.addEventListener("click", () => selectVideo(v.path));
      li.appendChild(btn);
      videoList.appendChild(li);
    }
  }

  async function startScan({ auto = false } = {}) {
    const dir = state.workspace;
    if (!dir) {
      showToast("Open a workspace folder first", false);
      return false;
    }
    const body = {
      dir,
      mode: scanModeSelect.value || "dji",
      recursive: !!scanRecursive.checked,
    };
    const res = await fetch("/api/scan/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showToast(data.detail || "Scan failed to start", false);
      return false;
    }
    showToast(
      auto
        ? `Auto-scan started (${data.mode})`
        : `Scan started (${data.mode}) → ${data.output || "CSV"}`
    );
    scheduleJobsPoll(1);
    return true;
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function segsForPath(path) {
    return state.segments.filter((s) => s.path === path);
  }

  function stopPolls() {
    if (state.previewPoll) {
      clearInterval(state.previewPoll);
      state.previewPoll = null;
    }
    if (state.filmstripPoll) {
      clearInterval(state.filmstripPoll);
      state.filmstripPoll = null;
    }
    if (state.cutPoll) {
      clearInterval(state.cutPoll);
      state.cutPoll = null;
    }
  }

  function setPreviewBanner(text, { building = false, error = false } = {}) {
    if (!text) {
      previewBanner.classList.add("hidden");
      previewBanner.textContent = "";
      previewBanner.classList.remove("building", "error");
      return;
    }
    previewBanner.textContent = text;
    previewBanner.classList.toggle("building", building);
    previewBanner.classList.toggle("error", error);
    previewBanner.classList.remove("hidden");
  }

  function showLoader(pct, { title, sub } = {}) {
    const n = Math.max(0, Math.min(100, Math.round(Number(pct) || 0)));
    if (title) loaderTitle.textContent = title;
    if (sub) loaderSub.textContent = sub;
    previewLoader.classList.remove("hidden");
    loaderFill.style.width = `${n}%`;
    loaderPct.textContent = `${n}%`;
    const bar = previewLoader.querySelector(".loader-bar");
    if (bar) bar.setAttribute("aria-valuenow", String(n));
  }

  function hideLoader() {
    previewLoader.classList.add("hidden");
  }

  function clearPlayer() {
    player.pause();
    player.removeAttribute("src");
    player.load();
    player.classList.add("hidden");
    stillWrap.classList.remove("hidden");
    state.usingProxy = false;
  }

  function currentTime() {
    if (state.usingProxy && player.src) return player.currentTime || 0;
    return state.scrubTime || 0;
  }

  function nearestFrame(t) {
    const frames = state.filmstripFrames;
    if (!frames.length) return null;
    let best = frames[0];
    let bestD = Math.abs(frames[0].t - t);
    for (const f of frames) {
      const d = Math.abs(f.t - t);
      if (d < bestD) {
        best = f;
        bestD = d;
      }
    }
    return best;
  }

  /** Last filmstrip tile always means true EOF — not the tile's nominal timestamp. */
  function isLastFilmstripChunk(t) {
    const frames = state.filmstripFrames;
    if (!frames.length) return false;
    const last = frames[frames.length - 1];
    const near = nearestFrame(t);
    return !!(near && near.t === last.t);
  }

  /** Out on last tile → file duration. In always keeps the tile timestamp. */
  function timeForOut(t) {
    if (isLastFilmstripChunk(t) && state.filmstripDuration > 0) {
      return state.filmstripDuration;
    }
    return t;
  }

  function timeForIn(t) {
    const near = nearestFrame(t);
    return near ? near.t : t;
  }

  function showStillAt(t) {
    const frames = state.filmstripFrames;
    const near = nearestFrame(t);
    // Keep scrub on the tile timestamp (so In never becomes EOF by accident).
    state.scrubTime = near ? near.t : t;
    const atEnd = !!(near && isLastFilmstripChunk(near.t) && state.filmstripDuration);
    stillTime.textContent = atEnd
      ? `${fmt(state.filmstripDuration)} (end)`
      : fmt(state.scrubTime);
    if (near) {
      still.src = near.url;
      filmstripEl.querySelectorAll("button").forEach((btn) => {
        const bt = Number(btn.dataset.t);
        const isLast = frames.length && bt === frames[frames.length - 1].t;
        btn.classList.toggle(
          "active",
          Math.abs(bt - state.scrubTime) < 0.05 || (isLast && atEnd),
        );
      });
    }
    if (state.usingProxy && player.src) {
      const seekTo = atEnd ? state.filmstripDuration : state.scrubTime;
      player.currentTime = Math.min(seekTo, player.duration || seekTo);
    }
  }

  /** In at ``fromTime``, Out at EOF — main delete-to-end helper. */
  function setInThroughEnd(fromTime) {
    const inT = timeForIn(fromTime);
    const outT = state.filmstripDuration || clipDuration();
    if (!outT || !(outT > inT)) {
      showToast("Pick an earlier point for In (not the last thumb)", false);
      return false;
    }
    state.markIn = inT;
    state.markOut = outT;
    showStillAt(inT);
    showToast(`In ${fmt(inT)} · Out end ${fmt(outT)}`);
    clearClipWindow();
    updateMarkUi();
    return true;
  }

  function setMarkOutToEnd() {
    const d = state.filmstripDuration || clipDuration();
    if (!d) {
      showToast("Duration unknown — wait for filmstrip", false);
      return;
    }
    state.markOut = d;
    if (state.markIn != null && state.markOut <= state.markIn) {
      showToast("Out must be after In — set In on an earlier thumb first", false);
      state.markOut = null;
    } else {
      showToast(`Out = end ${fmt(d)}`);
    }
    updateMarkUi();
  }

  function renderFilmstrip() {
    filmstripEl.innerHTML = "";
    const frames = state.filmstripFrames;
    if (!frames.length) return;
    const inT = state.markIn;
    const outT = state.markOut;
    for (const f of frames) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.t = String(f.t);
      const isLast = f.t === frames[frames.length - 1].t;
      btn.title = isLast ? `${fmt(f.t)} (end of file)` : fmt(f.t);
      btn.dataset.last = isLast ? "1" : "0";
      if (
        Math.abs(f.t - state.scrubTime) < 0.05 ||
        (isLast &&
          state.filmstripDuration &&
          state.scrubTime >= state.filmstripDuration - 0.05)
      ) {
        btn.classList.add("active");
      }
      if (
        inT != null &&
        outT != null &&
        f.t >= inT &&
        (f.t <= outT || (isLast && outT >= (state.filmstripDuration || outT) - 0.05))
      ) {
        btn.classList.add("in-range");
      }
      const img = document.createElement("img");
      img.src = f.url;
      img.alt = fmt(f.t);
      img.loading = "lazy";
      btn.appendChild(img);
      btn.addEventListener("click", (ev) => {
        clearClipWindow();
        if (ev.shiftKey) {
          // Shift+click = set Out here (last thumb → EOF).
          // In = where you plain-clicked before (current scrub before this seek).
          ev.preventDefault();
          const inT = timeForIn(state.scrubTime);
          const outT = timeForOut(f.t);
          showStillAt(f.t);
          state.markIn = inT;
          state.markOut = outT;
          if (!(state.markOut > state.markIn)) {
            showToast("Out must be after In — plain-click start first", false);
            state.markOut = null;
          } else {
            const outLabel =
              state.filmstripDuration &&
              state.markOut >= state.filmstripDuration - 0.05
                ? `${fmt(state.markOut)} (end)`
                : fmt(state.markOut);
            showToast(`In ${fmt(state.markIn)} · Out ${outLabel}`);
          }
          updateMarkUi();
          return;
        }
        // Plain click = seek only (this becomes In when you Shift+click Out).
        showStillAt(f.t);
      });
      filmstripEl.appendChild(btn);
    }
  }

  async function loadFilmstripMeta(path) {
    const q = encodeURIComponent(path);
    const res = await fetch(`/api/filmstrip/meta?path=${q}`);
    if (!res.ok) return false;
    const data = await res.json();
    state.filmstripFrames = data.frames || [];
    state.filmstripDuration = data.duration || 0;
    renderFilmstrip();
    if (state.filmstripFrames.length) {
      showStillAt(state.filmstripFrames[0].t);
    }
    hideLoader();
    setPreviewBanner(
      `Filmstrip ready · click start · Shift+click end (last = EOF)`,
    );
    renderTimeline();
    return true;
  }

  async function ensureFilmstrip(path) {
    stopPolls();
    clearPlayer();
    state.filmstripFrames = [];
    filmstripEl.innerHTML = "";
    still.removeAttribute("src");
    stillTime.textContent = "—";

    const q = encodeURIComponent(path);
    const statusRes = await fetch(`/api/filmstrip/status?path=${q}`);
    const status = await statusRes.json();
    if (status.status === "ready") {
      await loadFilmstripMeta(path);
      return;
    }
    if (status.status === "error") {
      hideLoader();
      setPreviewBanner(
        `Filmstrip failed — use Open in VLC. ${status.error || ""}`,
        { error: true },
      );
      return;
    }

    await fetch("/api/filmstrip/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    showLoader(0, {
      title: "Building filmstrip",
      sub: "Sparse seek thumbs · seconds, not a full re-encode · Open in VLC for fine scrub",
    });
    setPreviewBanner("Queued for filmstrip…", { building: true });

    state.filmstripPoll = setInterval(async () => {
      if (state.currentPath !== path) {
        stopPolls();
        return;
      }
      const res = await fetch(`/api/filmstrip/status?path=${q}`);
      const data = await res.json();
      if (data.status === "queued") {
        showLoader(0);
        setPreviewBanner("Queued (one filmstrip at a time)…", { building: true });
        return;
      }
      if (data.status === "building") {
        showLoader(data.progress || 0);
        setPreviewBanner(`Building filmstrip… ${Math.round(data.progress || 0)}%`, {
          building: true,
        });
        return;
      }
      stopPolls();
      if (data.status === "ready") {
        await loadFilmstripMeta(path);
        return;
      }
      hideLoader();
      setPreviewBanner(`Filmstrip failed — use Open in VLC. ${data.error || ""}`, {
        error: true,
      });
    }, 400);
  }

  function playSource(url) {
    state.usingProxy = true;
    stillWrap.classList.add("hidden");
    player.classList.remove("hidden");
    player.pause();
    player.src = url;
    setPreviewBanner("Continuous proxy ready — scrub in the player, or use filmstrip");
  }

  async function ensureSmoothPreview(path) {
    stopPolls();
    const q = encodeURIComponent(path);
    const statusRes = await fetch(`/api/preview/status?path=${q}`);
    const status = await statusRes.json();
    if (status.status === "ready") {
      hideLoader();
      playSource(`/api/preview?path=${q}`);
      return;
    }
    if (status.status === "error") {
      hideLoader();
      setPreviewBanner(
        `Proxy failed — stick with filmstrip / VLC. ${status.error || ""}`,
        { error: true },
      );
      return;
    }
    await fetch("/api/preview/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    showLoader(0, {
      title: "Building continuous proxy",
      sub: "Full-timeline GPU encode — slow on long 4K · filmstrip stays usable",
    });
    setPreviewBanner("Queued for continuous proxy…", { building: true });
    state.previewPoll = setInterval(async () => {
      if (state.currentPath !== path) {
        stopPolls();
        return;
      }
      const res = await fetch(`/api/preview/status?path=${q}`);
      const data = await res.json();
      if (data.status === "queued") {
        showLoader(0);
        setPreviewBanner("Queued (one encode at a time)…", { building: true });
        return;
      }
      if (data.status === "building") {
        showLoader(data.progress || 0);
        setPreviewBanner(`Building proxy… ${Math.round(data.progress || 0)}%`, {
          building: true,
        });
        return;
      }
      stopPolls();
      if (data.status === "ready") {
        hideLoader();
        playSource(`/api/preview?path=${q}`);
        return;
      }
      hideLoader();
      setPreviewBanner(`Proxy failed — use filmstrip / VLC. ${data.error || ""}`, {
        error: true,
      });
    }, 1000);
  }

  function selectVideo(path) {
    state.currentPath = path;
    state.clip = null;
    state.markIn = null;
    state.markOut = null;
    state.scrubTime = 0;
    updateMarkUi();
    emptyMain.classList.add("hidden");
    workspace.classList.remove("hidden");
    currentName.textContent = path.split(/[/\\]/).pop();
    renderSidebar();
    renderSegments();
    renderTimeline();
    ensureFilmstrip(path);
  }

  function highlightSegment(index) {
    document.querySelectorAll(".seg").forEach((el) => {
      el.classList.toggle("active", Number(el.dataset.index) === index);
    });
  }

  /** Jump to segment start (filmstrip still or proxy play window). */
  function playSegment(seg) {
    state.clip = { start: seg.seg_start, end: seg.seg_end, index: seg.index };
    highlightSegment(seg.index);
    const start = Math.max(0, seg.seg_start);
    showStillAt(start);
    if (state.usingProxy && player.src) {
      const apply = () => {
        player.currentTime = start;
        player.play().catch(() => {});
      };
      if (player.readyState >= 1) apply();
      else player.addEventListener("loadedmetadata", apply, { once: true });
    }
  }

  function clearClipWindow() {
    state.clip = null;
  }

  player.addEventListener("timeupdate", () => {
    if (state.usingProxy) {
      state.scrubTime = player.currentTime || 0;
      stillTime.textContent = fmt(state.scrubTime);
    }
    const clip = state.clip;
    if (!clip) return;
    if (player.currentTime >= clip.end - 0.04) {
      player.pause();
      player.currentTime = clip.end;
    }
  });

  player.addEventListener("seeking", () => {
    const clip = state.clip;
    if (!clip) return;
    if (player.currentTime < clip.start - 0.25 || player.currentTime > clip.end + 0.25) {
      clearClipWindow();
      document.querySelectorAll(".seg").forEach((el) => el.classList.remove("active"));
    }
  });

  function updateMarkUi() {
    const outLabel =
      state.markOut == null
        ? "—"
        : state.filmstripDuration && state.markOut >= state.filmstripDuration - 0.05
          ? `${fmt(state.markOut)} (end)`
          : fmt(state.markOut);
    markInLabel.textContent = state.markIn == null ? "—" : fmt(state.markIn);
    markOutLabel.textContent = outLabel;
    const ok =
      state.markIn != null &&
      state.markOut != null &&
      state.markOut > state.markIn;
    btnSaveCut.disabled = !ok;
    renderTimeline();
    renderFilmstrip();
  }

  function setMarkIn() {
    state.markIn = timeForIn(currentTime());
    if (state.markOut != null && state.markOut <= state.markIn) state.markOut = null;
    updateMarkUi();
  }

  function setMarkOut() {
    // Last filmstrip chunk = end of file, always.
    state.markOut = timeForOut(currentTime());
    if (state.markIn != null && state.markOut <= state.markIn) {
      showToast("Out must be after In", false);
      state.markOut = null;
    }
    updateMarkUi();
  }

  async function saveCut() {
    if (
      !state.currentPath ||
      state.markIn == null ||
      state.markOut == null ||
      state.markOut <= state.markIn
    ) {
      return;
    }
    const path = state.currentPath;
    const start = timeForIn(state.markIn);
    // Re-snap Out if it was the last chunk.
    const end = timeForOut(state.markOut);
    state.markIn = start;
    state.markOut = end;
    if (!(end > start)) {
      showToast("Out must be after In", false);
      updateMarkUi();
      return;
    }
    updateMarkUi();
    btnSaveCut.disabled = true;

    const strategyLabel = (s) => {
      if (s === "keep-head") return "Cheap keep-head (delete to end)";
      if (s === "keep-tail") return "Cheap keep-tail (delete from start)";
      if (s === "middle-concat") return "Middle delete (concat)";
      return "Lossless delete";
    };

    showLoader(0, {
      title: "Deleting range",
      sub: "Lossless stream copy · writing next to source",
    });
    setPreviewBanner("Starting delete…", { building: true });
    showToast("Deleting range…");

    const res = await fetch("/api/quickcut", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, start, end }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      hideLoader();
      setPreviewBanner(data.detail || "Cut failed", { error: true });
      showToast(data.detail || "Cut failed", false);
      updateMarkUi();
      return;
    }

    const label = strategyLabel(data.strategy);
    showLoader(data.progress || 0, {
      title: "Deleting range",
      sub: `${label} → ${data.output || "same folder"}`,
    });
    setPreviewBanner(`${label}…`, { building: true });

    if (data.status === "ready") {
      hideLoader();
      setPreviewBanner(`Saved ${data.output}`);
      showToast(`Saved ${data.output}`);
      updateMarkUi();
      return;
    }
    if (data.status === "error") {
      hideLoader();
      setPreviewBanner(data.error || "Cut failed", { error: true });
      showToast(data.error || "Cut failed", false);
      updateMarkUi();
      return;
    }

    const q = encodeURIComponent(path);
    if (state.cutPoll) clearInterval(state.cutPoll);
    state.cutPoll = setInterval(async () => {
      const st = await fetch(`/api/quickcut/status?path=${q}`);
      const info = await st.json().catch(() => ({}));
      if (info.status === "queued") {
        showLoader(0);
        setPreviewBanner(`Queued: ${strategyLabel(info.strategy)}…`, { building: true });
        return;
      }
      if (info.status === "running") {
        showLoader(info.progress || 0);
        setPreviewBanner(
          `${strategyLabel(info.strategy)}… ${Math.round(info.progress || 0)}%`,
          { building: true },
        );
        return;
      }
      clearInterval(state.cutPoll);
      state.cutPoll = null;
      hideLoader();
      if (info.status === "ready") {
        setPreviewBanner(`Saved ${info.output}`);
        showToast(`Saved ${info.output}`);
        updateMarkUi();
        return;
      }
      setPreviewBanner(info.error || "Cut failed", { error: true });
      showToast(info.error || "Cut failed", false);
      updateMarkUi();
    }, 500);
  }

  function clipDuration() {
    const segs = segsForPath(state.currentPath);
    return segs[0]?.duration || state.filmstripDuration || player.duration || 1;
  }

  function renderTimeline() {
    const segs = segsForPath(state.currentPath);
    const duration = clipDuration();
    timeline.innerHTML = "";
    for (const s of segs) {
      const mark = document.createElement("div");
      mark.className = `mark ${s.action}`;
      mark.style.left = `${(s.seg_start / duration) * 100}%`;
      mark.style.width = `${Math.max(0.15, ((s.seg_end - s.seg_start) / duration) * 100)}%`;
      mark.title = `${fmt(s.seg_start)} – ${fmt(s.seg_end)} (${s.action})`;
      mark.addEventListener("click", (ev) => {
        ev.stopPropagation();
        playSegment(s);
      });
      timeline.appendChild(mark);
    }
    if (state.markIn != null && state.markOut != null && state.markOut > state.markIn) {
      const range = document.createElement("div");
      range.className = "mark cut-range";
      range.style.left = `${(state.markIn / duration) * 100}%`;
      range.style.width = `${((state.markOut - state.markIn) / duration) * 100}%`;
      range.title = `Delete ${fmt(state.markIn)} – ${fmt(state.markOut)}`;
      timeline.appendChild(range);
    } else {
      if (state.markIn != null) {
        const inn = document.createElement("div");
        inn.className = "mark cut-in";
        inn.style.left = `${(state.markIn / duration) * 100}%`;
        timeline.appendChild(inn);
      }
      if (state.markOut != null) {
        const out = document.createElement("div");
        out.className = "mark cut-out";
        out.style.left = `${(state.markOut / duration) * 100}%`;
        timeline.appendChild(out);
      }
    }
  }

  timeline.addEventListener("click", (ev) => {
    clearClipWindow();
    document.querySelectorAll(".seg").forEach((el) => el.classList.remove("active"));
    const duration = clipDuration();
    const rect = timeline.getBoundingClientRect();
    const ratio = (ev.clientX - rect.left) / rect.width;
    const t = Math.max(0, ratio * duration);
    showStillAt(t);
    if (state.usingProxy && player.src) {
      player.play().catch(() => {});
    }
  });

  function renderSegments() {
    const segs = segsForPath(state.currentPath);
    const activeIndex = state.clip?.index;
    segList.innerHTML = "";
    if (!segs.length) {
      segList.innerHTML =
        '<li class="empty">No scan segments for this file — use In/Out + Delete range</li>';
      return;
    }
    for (const s of segs) {
      const li = document.createElement("li");
      li.className = "seg" + (s.index === activeIndex ? " active" : "");
      li.dataset.index = String(s.index);
      li.innerHTML = `
        <div class="seg-main">
          <div class="seg-time">${fmt(s.seg_start)} → ${fmt(s.seg_end)}</div>
          <div class="seg-meta">
            ${s.dead_sec.toFixed(1)}s · ${s.confidence}
            · <span class="badge ${s.action}">${s.action}</span>
            · reviewed ${s.reviewed}
          </div>
        </div>
        <div class="seg-actions">
          <button type="button" class="btn small accept" data-act="remove">Accept</button>
          <button type="button" class="btn small reject" data-act="keep">Reject</button>
          <button type="button" class="btn small ghost" data-act="review">Later</button>
        </div>`;
      li.querySelector(".seg-main").addEventListener("click", () => playSegment(s));
      li.querySelectorAll("button[data-act]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          await setAction(s.index, btn.dataset.act);
        });
      });
      segList.appendChild(li);
    }
  }

  async function setAction(index, action) {
    const res = await fetch(`/api/segments/${index}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
    if (!res.ok) {
      alert("Failed to update segment");
      return;
    }
    const data = await res.json();
    const i = state.segments.findIndex((s) => s.index === index);
    if (i >= 0) state.segments[i] = data.segment;
    const st = await (await fetch("/api/state")).json();
    state.videos = st.videos;
    renderSidebar();
    renderSegments();
    renderTimeline();
  }

  async function setAll(action) {
    const segs = segsForPath(state.currentPath);
    for (const s of segs) {
      await setAction(s.index, action);
    }
  }

  document.getElementById("btn-accept-all").addEventListener("click", () => setAll("remove"));
  document.getElementById("btn-reject-all").addEventListener("click", () => setAll("keep"));
  document.getElementById("tab-segments").addEventListener("click", () => setSidebarMode("segments"));
  document.getElementById("tab-folder").addEventListener("click", () => setSidebarMode("folder"));

  async function applyWorkspace(path) {
    const res = await fetch("/api/workspace", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showToast(data.detail || "Could not open workspace", false);
      return;
    }
    showToast(`Workspace → ${data.workspace}`);
    await loadState();
    setSidebarMode("segments");
    await loadFolder(state.workspace);
  }

  async function cancelScan() {
    const res = await fetch("/api/scan/cancel", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showToast(data.detail || "Could not cancel scan", false);
      return;
    }
    showToast("Scan cancel requested");
    scheduleJobsPoll(1);
  }

  document.getElementById("btn-workspace-open").addEventListener("click", () => {
    openFolderPicker({
      title: "Open workspace",
      startDir: state.workspace,
      onSelect: async (path) => {
        await applyWorkspace(path);
      },
    });
  });
  document.getElementById("picker-close").addEventListener("click", closeFolderPicker);
  document.getElementById("picker-cancel").addEventListener("click", closeFolderPicker);
  document.getElementById("picker-select").addEventListener("click", confirmFolderPicker);
  document.getElementById("picker-go").addEventListener("click", () => {
    loadPickerDir(pickerPath.value.trim());
  });
  pickerUp.addEventListener("click", () => {
    if (pickerState.parent) loadPickerDir(pickerState.parent);
  });
  pickerPath.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      loadPickerDir(pickerPath.value.trim());
    }
  });
  folderPicker.addEventListener("click", (ev) => {
    if (ev.target === folderPicker) closeFolderPicker();
  });
  document.addEventListener("keydown", (ev) => {
    if (!pickerState.open) return;
    if (ev.key === "Escape") {
      ev.preventDefault();
      closeFolderPicker();
    }
  });
  btnScanStart.addEventListener("click", () => startScan());
  document.getElementById("btn-scan-stop").addEventListener("click", () => cancelScan());
  document.getElementById("btn-jobs-clear").addEventListener("click", async () => {
    const res = await fetch("/api/jobs/clear", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showToast(data.detail || "Could not clear jobs", false);
      return;
    }
    lastScanStatus = "";
    const n = data.removed || 0;
    showToast(n ? `Cleared ${n} finished job(s)` : "No finished jobs to clear");
    await refreshJobs();
  });
  document.getElementById("btn-mark-in").addEventListener("click", setMarkIn);
  document.getElementById("btn-mark-out").addEventListener("click", setMarkOut);
  document.getElementById("btn-mark-end").addEventListener("click", setMarkOutToEnd);
  document.getElementById("btn-save-cut").addEventListener("click", saveCut);
  document.getElementById("btn-build-proxy").addEventListener("click", () => {
    if (!state.currentPath) return;
    ensureSmoothPreview(state.currentPath);
  });
  document.getElementById("btn-open-mpv").addEventListener("click", async () => {
    if (!state.currentPath) return;
    const res = await fetch("/api/open-external", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: state.currentPath,
        time: currentTime(),
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showToast(data.detail || "mpv open failed", false);
      return;
    }
    showToast(`Opened in ${data.player || "player"} @ ${fmt(data.time || 0)}`);
  });

  const jobsList = document.getElementById("jobs-list");
  const jobsCount = document.getElementById("jobs-count");

  function kindLabel(kind, strategy) {
    if (kind === "cut") {
      if (strategy === "keep-head") return "cut·head";
      if (strategy === "keep-tail") return "cut·tail";
      if (strategy === "middle-concat") return "cut·mid";
      return "cut";
    }
    if (kind === "scan") {
      if (strategy) return `scan·${strategy}`;
      return "scan";
    }
    if (kind === "filmstrip") return "strip";
    if (kind === "proxy") return "proxy";
    return kind;
  }

  let lastScanStatus = "";

  function renderJobs(data) {
    const jobs = data.jobs || [];
    const active = data.active || 0;
    jobsCount.textContent = active ? `${active} active` : "idle";
    jobsCount.classList.toggle("idle", !active);
    if (!jobs.length) {
      jobsList.innerHTML = '<li class="jobs-empty">No background jobs</li>';
      return;
    }
    jobsList.innerHTML = "";
    for (const j of jobs) {
      const li = document.createElement("li");
      const st = String(j.status || "");
      li.className = "job-row" + (st === "error" ? " error" : st === "ready" ? " ready" : "");
      const pct = Math.max(0, Math.min(100, Math.round(Number(j.progress) || 0)));
      const meta =
        j.error ||
        j.detail ||
        (j.output ? String(j.output).split(/[/\\]/).pop() : "") ||
        `${pct}%`;
      li.innerHTML =
        `<div class="job-top">` +
        `<span class="job-kind">${escapeHtml(kindLabel(j.kind, j.strategy))}</span>` +
        `<span class="job-status">${escapeHtml(st)} ${pct}%</span>` +
        `</div>` +
        `<div class="job-name" title="${escapeHtml(j.path || "")}">${escapeHtml(j.name || "?")}</div>` +
        `<div class="job-bar"><span style="width:${pct}%"></span></div>` +
        (meta
          ? `<div class="job-meta">${escapeHtml(meta)}</div>`
          : "");
      li.addEventListener("click", () => {
        if (j.kind === "scan") {
          setSidebarMode("segments");
          return;
        }
        if (j.path) selectVideo(j.path);
      });
      jobsList.appendChild(li);
    }
  }

  async function refreshJobs() {
    try {
      const res = await fetch("/api/jobs");
      if (!res.ok) return;
      const data = await res.json();
      renderJobs(data);
      const scanJob = (data.jobs || []).find((j) => j.kind === "scan");
      if (scanJob) {
        const key = `${scanJob.status}:${scanJob.progress}:${scanJob.error || ""}`;
        if (
          scanJob.status === "ready" &&
          lastScanStatus &&
          !lastScanStatus.startsWith("ready")
        ) {
          showToast("Scan finished");
          await refreshSegments();
          setSidebarMode("segments");
        } else if (scanJob.status === "error" && lastScanStatus !== key) {
          showToast(scanJob.error || "Scan failed", false);
        } else if (
          scanJob.status === "cancelled" &&
          lastScanStatus &&
          !lastScanStatus.startsWith("cancelled")
        ) {
          showToast("Scan cancelled");
        }
        lastScanStatus = key;
      }
      return data.active || 0;
    } catch {
      return 0;
    }
  }

  let jobsTimer = null;
  function scheduleJobsPoll(active) {
    if (jobsTimer) clearTimeout(jobsTimer);
    jobsTimer = setTimeout(async () => {
      const n = await refreshJobs();
      if (state.sidebarMode === "segments") {
        await refreshSegments({ reread: n > 0 });
      }
      scheduleJobsPoll(n);
    }, active ? 800 : 4000);
  }

  document.addEventListener("keydown", (ev) => {
    if (!state.currentPath) return;
    const tag = (ev.target && ev.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA") return;

    if (ev.key === "i" || ev.key === "I") {
      ev.preventDefault();
      setMarkIn();
    } else if (ev.key === "o" || ev.key === "O") {
      ev.preventDefault();
      setMarkOut();
    } else if (ev.key === "e" || ev.key === "E") {
      ev.preventDefault();
      setMarkOutToEnd();
    } else if (ev.key === "s" || ev.key === "S") {
      ev.preventDefault();
      setInThroughEnd(currentTime());
    } else if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
      const frames = state.filmstripFrames;
      if (!frames.length) return;
      ev.preventDefault();
      const cur = nearestFrame(state.scrubTime) || frames[0];
      const idx = frames.findIndex((f) => f.t === cur.t);
      const next =
        ev.key === "ArrowLeft"
          ? frames[Math.max(0, idx - 1)]
          : frames[Math.min(frames.length - 1, idx + 1)];
      showStillAt(next.t);
    }
  });

  refreshJobs().then((n) => scheduleJobsPoll(n));
  loadState();
})();
