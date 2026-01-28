(() => {
  const fileInput = document.getElementById("file");
  const inferFpsInput = document.getElementById("inferFps");
  const btnDetect = document.getElementById("btnDetect");
  const btnClear = document.getElementById("btnClear");
  const btnStopOverlay = document.getElementById("btnStopOverlay");
  const btnClearDebug = document.getElementById("btnClearDebug");

  const video = document.getElementById("video");
  const canvas = document.getElementById("overlay");

  const countEl = document.getElementById("count");
  const tEl = document.getElementById("t");
  const statsEl = document.getElementById("stats");
  const infoEl = document.getElementById("info");
  const debugEl = document.getElementById("debug");

  let currentFile = null;
  let timeline = [];
  let avgCount = 0;
  let maxCount = 0;

  let overlayVisible = true;

  function setInfo(s) { infoEl.textContent = s; }

  function setDebug(obj) {
    const s = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
    const MAX = 9000;
    debugEl.textContent = s.length > MAX ? (s.slice(0, MAX) + "\n…(truncated)") : s;
  }

  let lastIdx = -1;
  let rafId = null;
  let vfcId = null;

  function stopOverlayLoop() {
    if (rafId != null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    if (vfcId != null && typeof video.cancelVideoFrameCallback === "function") {
      try { video.cancelVideoFrameCallback(vfcId); } catch {}
    }
    vfcId = null;
  }

  function startOverlayLoop() {
    stopOverlayLoop();

    if (typeof video.requestVideoFrameCallback === "function") {
      const tick = () => {
        updateOverlayFromCurrentTime(true);
        vfcId = video.requestVideoFrameCallback(tick);
      };
      vfcId = video.requestVideoFrameCallback(tick);
      return;
    }

    const tick = () => {
      updateOverlayFromCurrentTime(true);
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
  }

  btnClearDebug.addEventListener("click", () => (debugEl.textContent = ""));

  function resizeCanvasToVideo() {
    const rect = video.getBoundingClientRect();
    canvas.style.width = rect.width + "px";
    canvas.style.height = rect.height + "px";

    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(rect.width * dpr));
    canvas.height = Math.max(1, Math.round(rect.height * dpr));
  }

  function clearOverlay() {
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  function findNearestIndex(t) {
    const n = timeline.length;
    if (n === 0) return -1;

    let lo = 0, hi = n - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const mt = timeline[mid].t;
      if (mt < t) lo = mid + 1;
      else hi = mid - 1;
    }
    if (hi < 0) return 0;
    if (lo >= n) return n - 1;
    return (t - timeline[hi].t) <= (timeline[lo].t - t) ? hi : lo;
  }

  function drawBoxes(boxes) {
    if (!overlayVisible) {
      clearOverlay();
      return;
    }
    if (!video.videoWidth || !video.videoHeight) return;

    resizeCanvasToVideo();

    const rect = video.getBoundingClientRect();
    const sx = rect.width / video.videoWidth;
    const sy = rect.height / video.videoHeight;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, rect.width, rect.height);

    ctx.lineWidth = 2;
    ctx.font = "12px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace";

    for (const b of boxes || []) {
      const x = b.x1 * sx;
      const y = b.y1 * sy;
      const w = (b.x2 - b.x1) * sx;
      const h = (b.y2 - b.y1) * sy;

      ctx.strokeStyle = "#34d399";
      ctx.strokeRect(x, y, w, h);

      const cls = b.cls_name ?? "bicycle";
      const conf = (typeof b.conf === "number") ? b.conf : 0;
      const label = `${cls} ${(conf * 100).toFixed(1)}%`;

      const pad = 3;
      const tw = ctx.measureText(label).width;

      const bx = Math.max(0, Math.min(rect.width - (tw + pad * 2), x));
      const by = Math.max(0, y - 16);

      ctx.fillStyle = "rgba(0,0,0,0.65)";
      ctx.fillRect(bx, by, tw + pad * 2, 16);

      ctx.fillStyle = "#e5e7eb";
      ctx.fillText(label, bx + pad, by + 12);
    }
  }

  function updateOverlayFromCurrentTime(onlyIfChanged = false) {
    if (!timeline.length) {
      clearOverlay();
      countEl.textContent = "-";
      tEl.textContent = "-";
      lastIdx = -1;
      return;
    }

    const t = video.currentTime || 0;
    const idx = findNearestIndex(t);
    if (idx < 0) return;

    if (onlyIfChanged && idx === lastIdx) return;
    lastIdx = idx;

    const item = timeline[idx];
    const boxes = item.boxes || [];

    countEl.textContent = String(item.count ?? "-");
    tEl.textContent = `${item.t.toFixed(2)}s (video: ${t.toFixed(2)}s)`;
    drawBoxes(boxes);
  }

  async function detectVideo() {
    if (!currentFile) return;

    btnDetect.disabled = true;
    setInfo("Загрузка + детекция (это может занять некоторое время)...");

    try {
      const inferFps = Number(inferFpsInput.value || 2);
      const fd = new FormData();
      fd.append("file", currentFile);

      const url = `/api/count/video?include_boxes=true&infer_fps=${encodeURIComponent(inferFps)}`;

      const resp = await fetch(url, { method: "POST", body: fd });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || "Detection failed");

      timeline = Array.isArray(data.timeline) ? data.timeline : [];
      avgCount = data.avg_count || 0;
      maxCount = data.max_count || 0;

      statsEl.textContent = `avg=${avgCount.toFixed(2)} max=${maxCount}`;
      setInfo(`Готово ✅ frames_processed=${data.frames_processed}, infer_fps=${data.infer_fps}`);

      setDebug({
        frames_processed: data.frames_processed,
        infer_fps: data.infer_fps,
        include_boxes: data.include_boxes,
        avg_count: data.avg_count,
        max_count: data.max_count,
        timeline_len: timeline.length,
      });

      updateOverlayFromCurrentTime();
    } catch (e) {
      setInfo("Ошибка: " + String(e));
      timeline = [];
      avgCount = 0;
      maxCount = 0;
      statsEl.textContent = "-";
      clearOverlay();
      setDebug({ error: String(e) });
    } finally {
      btnDetect.disabled = false;
    }
  }

  function resetUiForNewFile() {
    timeline = [];
    clearOverlay();
    countEl.textContent = "-";
    tEl.textContent = "-";
    statsEl.textContent = "-";
  }

  function clearAll() {
    currentFile = null;
    resetUiForNewFile();
    setDebug("");
    setInfo("Выберите видео");
    btnDetect.disabled = true;
    btnClear.disabled = true;

    video.pause();
    video.removeAttribute("src");
    video.load();
  }

  fileInput.addEventListener("change", () => {
    const f = fileInput.files && fileInput.files[0];
    currentFile = f || null;

    resetUiForNewFile();

    if (!currentFile) {
      btnDetect.disabled = true;
      btnClear.disabled = true;
      setInfo("Выберите видео");
      video.removeAttribute("src");
      return;
    }

    btnDetect.disabled = false;
    btnClear.disabled = false;
    setInfo("Готово");

    const url = URL.createObjectURL(currentFile);
    video.src = url;
    video.load();
  });

  btnDetect.addEventListener("click", detectVideo);

  btnClear.addEventListener("click", clearAll);

  btnStopOverlay.addEventListener("click", () => {
    overlayVisible = !overlayVisible;
    btnStopOverlay.textContent = overlayVisible ? "Скрыть оверлей" : "Показать оверлей";
    updateOverlayFromCurrentTime();
  });

  video.addEventListener("play", () => {
    startOverlayLoop();
  });

  video.addEventListener("pause", () => {
    stopOverlayLoop();
    updateOverlayFromCurrentTime(false);
  });

  video.addEventListener("ended", () => {
    stopOverlayLoop();
  });

  video.addEventListener("seeked", () => {
    updateOverlayFromCurrentTime(false);
  });

  video.addEventListener("loadedmetadata", () => {
    resizeCanvasToVideo();
    updateOverlayFromCurrentTime(false);
  });

  window.addEventListener("resize", () => {
    resizeCanvasToVideo();
    updateOverlayFromCurrentTime(false);
  });

  clearAll();
})();
