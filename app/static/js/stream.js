(() => {
  const inputUrl = document.getElementById("inputUrl");
  const btnStart = document.getElementById("btnStart");
  const btnStop = document.getElementById("btnStop");
  const btnReload = document.getElementById("btnReload");
  const btnStopPlayer = document.getElementById("btnStopPlayer");
  const btnClearLogs = document.getElementById("btnClearLogs");

  const statusEl = document.getElementById("status");
  const logsEl = document.getElementById("logs");
  const video = document.getElementById("video");

  let hls = null;

  function setStatus(obj) {
    statusEl.textContent = JSON.stringify(obj, null, 2);
  }

  const logLines = [];
  const MAX_LOG_LINES = 300;

  function appendLog(line) {
    const ts = new Date().toLocaleTimeString();
    logLines.push(`[${ts}] ${line}`);
    while (logLines.length > MAX_LOG_LINES) logLines.shift();
    logsEl.textContent = logLines.join("\n") + "\n";
    logsEl.scrollTop = logsEl.scrollHeight;
  }

  let startToken = 0;

  function setHlsBadge(state, extra = "") {
    const badge = document.getElementById("hlsBadge");
    if (!badge) return;

    const base = {
      idle:   ["HLS: простой",   "border-zinc-800 bg-zinc-900/50 text-zinc-300"],
      wait:   ["HLS: ожидание…", "border-amber-700/60 bg-amber-900/20 text-amber-200"],
      ready:  ["HLS: готов",     "border-emerald-700/60 bg-emerald-900/20 text-emerald-200"],
      error:  ["HLS: ошибка",    "border-rose-700/60 bg-rose-900/20 text-rose-200"],
    };

    const [label, classes] = base[state] || base.idle;
    badge.className = `inline-flex items-center rounded-full border px-2 py-1 ${classes}`;
    badge.textContent = extra ? `${label} (${extra})` : label;
  }

  async function fetchTextNoStore(url) {
    const resp = await fetch(url, {
      cache: "no-store",
      headers: { "Cache-Control": "no-store" },
    });
    if (!resp.ok) return null;
    return await resp.text();
  }

  function countSegmentsInM3U8(text) {
    const lines = text.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
    let n = 0;
    for (const ln of lines) {
      if (ln.startsWith("#")) continue;
      if (ln.endsWith(".ts") || ln.endsWith(".m4s")) n++;
    }
    return n;
  }

  async function waitForHlsReady(hlsUrl, token, { minSegments = 2, timeoutMs = 20000, pollMs = 500 } = {}) {
    const start = Date.now();
    setHlsBadge("wait", `0/${minSegments}`);

    while (Date.now() - start < timeoutMs) {
      if (token !== startToken) return { ok: false, cancelled: true };

      const url = `${hlsUrl}?_=${Date.now()}`;
      const text = await fetchTextNoStore(url);

      if (text) {
        const segs = countSegmentsInM3U8(text);
        setHlsBadge("wait", `${segs}/${minSegments}`);

        if (segs >= minSegments) {
          setHlsBadge("ready", `${segs} segs`);
          return { ok: true, segs };
        }
      }

      await new Promise(r => setTimeout(r, pollMs));
    }

    setHlsBadge("error", "timeout");
    return { ok: false, timeout: true };
  }

  function stopPlayer(reason = "stopped") {
    setHlsBadge("idle");

    try {
      if (hls) {
        hls.destroy();
        hls = null;
      }
    } catch {}

    try { video.pause(); } catch {}

    try {
      video.removeAttribute("src");
      video.load();
    } catch {}

    appendLog(`плеер остановлен (${reason})`);
  }

  function loadPlayer(hlsUrl) {
    const url = `${hlsUrl}?_=${Date.now()}`;
    appendLog(`загрузка: ${url}`);

    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = url;
      video.play().catch(() => {});
      appendLog("используется нативный HLS");
      return;
    }

    if (window.Hls && window.Hls.isSupported()) {
      hls = new Hls({
        lowLatencyMode: false,
        debug: false,
      });

      hls.on(Hls.Events.MEDIA_ATTACHED, () => appendLog("hls: медиа подключено"));
      hls.on(Hls.Events.MANIFEST_LOADING, (_, d) => appendLog(`hls: загрузка манифеста (${d.url})`));
      hls.on(Hls.Events.MANIFEST_PARSED, (_, d) => appendLog(`hls: манифест разобран (levels=${d.levels?.length ?? "?"})`));
      hls.on(Hls.Events.ERROR, (_, data) => {
        const payload = {
          type: data.type,
          details: data.details,
          fatal: data.fatal,
          reason: data.reason,
          mimeType: data.mimeType,
          sourceBufferName: data.sourceBufferName,
          error: data.error ? String(data.error) : null,
        };
        appendLog(`hls ошибка: ${JSON.stringify(payload)}`);
        setStatus({ ...safeLastStatus, player_error: payload });

        if (data.fatal) {
          if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
            appendLog("hls: фатальная сетевая ошибка → startLoad()");
            hls.startLoad();
          } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
            appendLog("hls: фатальная медиа ошибка → recoverMediaError()");
            hls.recoverMediaError();
          } else {
            appendLog("hls: фатальная ошибка → destroy()");
            stopPlayer("fatal");
          }
        }
      });

      hls.loadSource(url);
      hls.attachMedia(video);
      video.play().catch(() => {});
      appendLog("используется hls.js");
      return;
    }

    appendLog("HLS не поддерживается в этом браузере");
  }

  let safeLastStatus = {};

  async function startPipeline() {
    const url = inputUrl.value.trim();
    if (!url) return;

    const resp = await fetch("/api/stream/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input_url: url }),
    });

    const data = await resp.json();
    safeLastStatus = data;
    setStatus(data);

    if (!resp.ok) {
      appendLog(`ошибка запуска: ${data.detail || "ошибка"}`);
      return;
    }

    startToken++;
    const token = startToken;

    appendLog("пайплайн запущен; ожидание сегментов HLS плейлиста…");

    const ready = await waitForHlsReady(data.hls_url, token, {
      minSegments: 2,
      timeoutMs: 25000,
      pollMs: 500,
    });

    if (!ready.ok) {
      if (ready.cancelled) {
        appendLog("ожидание HLS отменено");
        return;
      }
      appendLog("HLS не готов (таймаут/ошибка). Проверьте статус бэкенда.");
      return;
    }

    loadPlayer(data.hls_url);
  }

  async function stopPipeline() {
    startToken++;
    setHlsBadge("idle");

    const resp = await fetch("/api/stream/stop", { method: "POST" });
    const data = await resp.json();
    safeLastStatus = data;
    setStatus(data);

    stopPlayer("pipeline stopped");
  }

  async function pollStatus() {
    try {
      const resp = await fetch("/api/stream/status");
      const data = await resp.json();
      safeLastStatus = data;
      setStatus(data);
    } catch {}
    setTimeout(pollStatus, 1000);
  }

  btnStart.addEventListener("click", startPipeline);
  btnStop.addEventListener("click", stopPipeline);

  btnReload.addEventListener("click", async () => {
    try {
      startToken++;
      const token = startToken;

      stopPlayer("reload");

      const st = await (await fetch("/api/stream/status")).json();
      safeLastStatus = st;
      setStatus(st);

      if (!st || !st.hls_url) {
        appendLog("перезагрузка: нет hls_url в статусе");
        setHlsBadge("error", "нет hls_url");
        return;
      }

      appendLog("перезагрузка: ожидание готовности HLS…");
      const ready = await waitForHlsReady(st.hls_url, token, {
        minSegments: 2,
        timeoutMs: 25000,
        pollMs: 500,
      });

      if (!ready.ok) {
        if (ready.cancelled) {
          appendLog("перезагрузка: ожидание HLS отменено");
          return;
        }
        appendLog("перезагрузка: HLS не готов (таймаут/ошибка)");
        return;
      }

      loadPlayer(st.hls_url);
    } catch (e) {
      appendLog(`ошибка перезагрузки: ${String(e)}`);
      setHlsBadge("error", "ошибка перезагрузки");
    }
  });

  btnStopPlayer.addEventListener("click", () => stopPlayer("user"));
  btnClearLogs.addEventListener("click", () => (logsEl.textContent = ""));

  if (!inputUrl.value) inputUrl.value = "rtsp://127.0.0.1:8554/bikes";

  pollStatus();
})();
