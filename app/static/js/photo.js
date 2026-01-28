(() => {
  const API_URL = "/api/count/photo";

  const els = {
    fileInput: document.getElementById("fileInput"),
    btnDetect: document.getElementById("btnDetect"),
    btnClear: document.getElementById("btnClear"),
    btnClearStatus: document.getElementById("btnClearStatus"),

    roiEnabled: document.getElementById("roiEnabled"),
    btnEditRoi: document.getElementById("btnEditRoi"),
    btnClearRoi: document.getElementById("btnClearRoi"),
    roiCount: document.getElementById("roiCount"),
    roiMode: document.getElementById("roiMode"),

    count: document.getElementById("count"),
    boxCount: document.getElementById("boxCount"),
    status: document.getElementById("status"),

    img: document.getElementById("img"),
    overlay: document.getElementById("overlay"),
  };

  function setStatus(obj) {
    const s = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
    const MAX = 9000;
    els.status.textContent = s.length > MAX ? (s.slice(0, MAX) + "\n…(truncated)") : s;
  }
  els.btnClearStatus.addEventListener("click", () => (els.status.textContent = ""));

  let file = null;
  let imgW = 0;
  let imgH = 0;

  let boxes = [];
  let roiPts = [];
  let roiEdit = false;
  let dragIdx = -1;

  function setRoiModeBadge(mode) {
    els.roiMode.textContent = mode;
    const base = "ml-2 rounded-full border px-2 py-0.5 text-[11px]";
    if (mode === "edit") {
      els.roiMode.className = `${base} border-amber-700/60 bg-amber-900/20 text-amber-200`;
    } else {
      els.roiMode.className = `${base} border-zinc-800 bg-zinc-900/50 text-zinc-300`;
    }
  }

  function updateUiEnabled() {
    const hasFile = !!file;
    els.btnDetect.disabled = !hasFile;
    els.btnClear.disabled = !hasFile;
    els.btnEditRoi.disabled = !hasFile;
    els.btnClearRoi.disabled = roiPts.length === 0;
    els.roiCount.textContent = String(roiPts.length);
    setRoiModeBadge(roiEdit ? "редактирование" : "простой");
  }

  function resetResults() {
    boxes = [];
    els.count.textContent = "-";
    els.boxCount.textContent = "-";
  }

  function clearAll() {
    file = null;
    imgW = 0;
    imgH = 0;
    boxes = [];
    roiPts = [];
    roiEdit = false;
    dragIdx = -1;

    els.img.removeAttribute("src");
    els.overlay.width = 0;
    els.overlay.height = 0;

    resetResults();
    setStatus("");
    updateUiEnabled();
  }

  els.btnClear.addEventListener("click", clearAll);

  function canvasSizeToImage() {
    const rect = els.img.getBoundingClientRect();
    const w = Math.max(1, Math.round(rect.width));
    const h = Math.max(1, Math.round(rect.height));
    if (els.overlay.width !== w || els.overlay.height !== h) {
      els.overlay.width = w;
      els.overlay.height = h;
    }
    return { w, h };
  }

  function dispToImg(x, y) {
    const { w, h } = canvasSizeToImage();
    return { x: (x / w) * imgW, y: (y / h) * imgH };
  }

  function imgToDisp(x, y) {
    const { w, h } = canvasSizeToImage();
    return { x: (x / imgW) * w, y: (y / imgH) * h };
  }

  function draw() {
    if (!imgW || !imgH) return;
    const ctx = els.overlay.getContext("2d");
    if (!ctx) return;

    const { w, h } = canvasSizeToImage();
    ctx.clearRect(0, 0, w, h);

    ctx.lineWidth = 2;
    ctx.font = "12px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace";
    for (const b of boxes) {
      const p1 = imgToDisp(b.x1, b.y1);
      const p2 = imgToDisp(b.x2, b.y2);

      ctx.strokeStyle = "#34d399";
      ctx.strokeRect(p1.x, p1.y, p2.x - p1.x, p2.y - p1.y);

      const label = `${b.cls_name ?? "bicycle"} ${(b.conf ?? 0).toFixed(2)}`;
      const tw = ctx.measureText(label).width;
      const tx = Math.max(0, Math.min(w - (tw + 10), p1.x));
      const ty = Math.max(14, p1.y);

      ctx.fillStyle = "rgba(0,0,0,0.65)";
      ctx.fillRect(tx, ty - 14, tw + 10, 16);
      ctx.fillStyle = "#e5e7eb";
      ctx.fillText(label, tx + 5, ty - 2);
    }

    if (roiPts.length > 0) {
      const pts = roiPts.map(p => imgToDisp(p.x, p.y));

      ctx.strokeStyle = roiEdit ? "#fbbf24" : "#a78bfa";
      ctx.fillStyle = roiEdit ? "rgba(251,191,36,0.10)" : "rgba(167,139,250,0.10)";
      ctx.lineWidth = 2;

      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
      if (pts.length >= 3) ctx.closePath();
      ctx.fill();
      ctx.stroke();

      for (let i = 0; i < pts.length; i++) {
        const p = pts[i];
        ctx.beginPath();
        ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
        ctx.fillStyle = roiEdit ? "#fbbf24" : "#a78bfa";
        ctx.fill();
        ctx.strokeStyle = "rgba(0,0,0,0.6)";
        ctx.stroke();
      }
    }
  }

  window.addEventListener("resize", () => draw());

  function hitTestPoint(dispX, dispY) {
    const r = 8;
    for (let i = 0; i < roiPts.length; i++) {
      const p = imgToDisp(roiPts[i].x, roiPts[i].y);
      const dx = dispX - p.x;
      const dy = dispY - p.y;
      if ((dx * dx + dy * dy) <= r * r) return i;
    }
    return -1;
  }

  els.btnEditRoi.addEventListener("click", () => {
    if (!file) return;
    roiEdit = !roiEdit;
    dragIdx = -1;
    updateUiEnabled();
    draw();
    setStatus(roiEdit ? "Редактирование ROI: ВКЛ" : "Редактирование ROI: ВЫКЛ");
  });

  els.btnClearRoi.addEventListener("click", () => {
    roiPts = [];
    dragIdx = -1;
    updateUiEnabled();
    draw();
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && roiEdit) {
      roiEdit = false;
      dragIdx = -1;
      updateUiEnabled();
      draw();
      setStatus("Редактирование ROI: ВЫКЛ");
    }
  });

  els.overlay.addEventListener("pointerdown", (e) => {
    if (!roiEdit || !imgW) return;
    const rect = els.overlay.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const idx = hitTestPoint(x, y);
    if (idx >= 0) {
      dragIdx = idx;
      els.overlay.setPointerCapture(e.pointerId);
      e.preventDefault();
      return;
    }

    const p = dispToImg(x, y);
    roiPts.push({ x: p.x, y: p.y });
    updateUiEnabled();
    draw();
  });

  els.overlay.addEventListener("pointermove", (e) => {
    if (!roiEdit || dragIdx < 0 || !imgW) return;
    const rect = els.overlay.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const p = dispToImg(x, y);
    roiPts[dragIdx] = {
      x: Math.max(0, Math.min(imgW - 1, p.x)),
      y: Math.max(0, Math.min(imgH - 1, p.y)),
    };
    draw();
  });

  els.overlay.addEventListener("pointerup", (e) => {
    if (dragIdx >= 0) {
      dragIdx = -1;
      try { els.overlay.releasePointerCapture(e.pointerId); } catch {}
      updateUiEnabled();
      draw();
    }
  });

  els.fileInput.addEventListener("change", () => {
    const f = els.fileInput.files && els.fileInput.files[0];
    if (!f) return;

    file = f;
    resetResults();
    roiPts = [];
    roiEdit = false;
    dragIdx = -1;

    const url = URL.createObjectURL(f);
    els.img.onload = () => {
      imgW = els.img.naturalWidth;
      imgH = els.img.naturalHeight;
      updateUiEnabled();
      draw();
      setStatus({ loaded: true, width: imgW, height: imgH });
    };
    els.img.src = url;

    updateUiEnabled();
  });

  els.btnDetect.addEventListener("click", async () => {
    if (!file) return;
    setStatus("Загрузка…");
    resetResults();

    try {
      const fd = new FormData();
      fd.append("file", file);

      const useRoi = els.roiEnabled.checked && roiPts.length >= 3;
      fd.append("roi_enabled", useRoi ? "true" : "false");

      if (useRoi) {
        const roiNorm = roiPts.map(p => [p.x / imgW, p.y / imgH]);
        fd.append("roi", JSON.stringify(roiNorm));
        fd.append("roi_format", "norm");
      }

      const resp = await fetch(API_URL, { method: "POST", body: fd });
      const data = await resp.json().catch(() => ({}));

      if (!resp.ok) {
        setStatus({ error: true, status: resp.status, data });
        return;
      }

      boxes = Array.isArray(data.boxes) ? data.boxes : [];
      els.count.textContent = String(data.count ?? "-");
      els.boxCount.textContent = String(boxes.length);

      setStatus({ ok: true, count: data.count, boxes: boxes.length, roi_sent: useRoi });
      draw();
    } catch (e) {
      setStatus({ error: true, message: String(e) });
    }
  });

  clearAll();
})();
