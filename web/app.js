(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const root = document.documentElement;
  const themeToggle = $("theme-toggle");
  const TOKEN_KEY = "dicomflow-access-token";

  function getTheme() {
    return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function setTheme(theme) {
    root.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("dicomflow-theme", theme);
    } catch (_) {}
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", theme === "dark" ? "#0b0b10" : "#f8fafc");
    if (themeToggle) {
      themeToggle.setAttribute(
        "aria-label",
        theme === "dark" ? "切换到浅色主题" : "切换到深色主题"
      );
      themeToggle.title = theme === "dark" ? "浅色模式" : "深色模式";
    }
  }

  themeToggle?.addEventListener("click", () => {
    setTheme(getTheme() === "dark" ? "light" : "dark");
  });
  setTheme(getTheme());

  // ── Access token (public deploy) ─────────────────────────
  function getToken() {
    try {
      return sessionStorage.getItem(TOKEN_KEY) || "";
    } catch {
      return "";
    }
  }
  function setToken(t) {
    try {
      if (t) sessionStorage.setItem(TOKEN_KEY, t);
      else sessionStorage.removeItem(TOKEN_KEY);
    } catch (_) {}
  }

  function authHeaders(extra) {
    const h = Object.assign({}, extra || {});
    const t = getToken();
    if (t) h["X-DicomFlow-Token"] = t;
    return h;
  }

  /** Server-side check: password is only accepted if middleware returns 200. */
  async function verifyAccessToken(token) {
    const t = (token || "").trim();
    if (!t) return false;
    try {
      const res = await fetch("/api/v1/auth/check", {
        headers: { "X-DicomFlow-Token": t },
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  function showAuthOverlay(message) {
    const overlay = $("auth-overlay");
    const err = $("auth-error");
    if (!overlay) return Promise.reject(new Error("auth UI missing"));
    overlay.hidden = false;
    if (err) {
      if (message) {
        err.hidden = false;
        err.textContent = message;
      } else {
        err.hidden = true;
        err.textContent = "";
      }
    }
    const input = $("auth-token-input");
    if (input) {
      // Do not prefill a previously rejected/wrong token
      if (!message) input.value = "";
      setTimeout(() => input.focus(), 50);
    }
    return new Promise((resolve) => {
      const submit = $("auth-submit");
      let busy = false;
      const cleanup = () => {
        submit?.removeEventListener("click", onSubmit);
        input?.removeEventListener("keydown", onKey);
      };
      const onSubmit = async () => {
        if (busy) return;
        const v = (input && input.value ? input.value : "").trim();
        if (!v) {
          if (err) {
            err.hidden = false;
            err.textContent = "请输入访问密码";
          }
          return;
        }
        busy = true;
        if (submit) submit.disabled = true;
        if (err) {
          err.hidden = false;
          err.textContent = "正在验证…";
        }
        const ok = await verifyAccessToken(v);
        busy = false;
        if (submit) submit.disabled = false;
        if (!ok) {
          setToken("");
          if (err) {
            err.hidden = false;
            err.textContent = "密码不正确，请重新输入";
          }
          if (input) {
            input.select();
            input.focus();
          }
          return;
        }
        setToken(v);
        overlay.hidden = true;
        if (err) {
          err.hidden = true;
          err.textContent = "";
        }
        cleanup();
        resolve(v);
      };
      const onKey = (e) => {
        if (e.key === "Enter") onSubmit();
      };
      submit?.addEventListener("click", onSubmit);
      input?.addEventListener("keydown", onKey);
    });
  }

  // ── Turnstile captcha (optional, server-toggled) ─────────
  // When enabled: must pass captcha BEFORE file pick / drop / upload.
  const captchaState = {
    enabled: false,
    siteKey: "",
    token: "",
    widgetId: null,
    scriptLoading: null,
  };

  const dropzone = $("dropzone");
  const fileInput = $("file-input");
  const dropLabel = $("drop-label");
  const dropHint = $("drop-hint");
  const fileChip = $("file-chip");
  const fileNameEl = $("file-name");
  const fileSizeEl = $("file-size");
  const clearFileBtn = $("clear-file-btn");
  const uploadBadge = $("upload-status-badge");
  const uploadBar = $("upload-progress-bar");
  const uploadWrap = $("upload-progress-wrap");
  const uploadPct = $("upload-pct");
  const uploadMsg = $("upload-msg");
  const convertBtn = $("convert-btn");
  const convertHint = $("convert-hint");
  const processBar = $("process-progress-bar");
  const processWrap = $("process-progress-wrap");
  const processPct = $("process-pct");
  const processMsg = $("process-msg");
  const processMeta = $("process-meta");
  const errorBox = $("error-box");
  const resultPanel = $("result-panel");
  const downloadBtn = $("download-btn");
  const fileList = $("file-list");
  const previewEmpty = $("preview-empty");
  const previewVideo = $("preview-video");
  const previewImage = $("preview-image");

  function getCaptchaToken() {
    if (!captchaState.enabled) return "";
    if (captchaState.token) return captchaState.token;
    const input = document.querySelector(
      'input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]'
    );
    return input && input.value ? input.value : "";
  }

  /** When captcha is on, upload zone stays locked until a valid token exists. */
  function isUploadUnlocked() {
    if (!captchaState.enabled) return true;
    return Boolean(getCaptchaToken());
  }

  function focusCaptchaGate(message) {
    const wrap = $("captcha-wrap");
    wrap?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    if (message) {
      setError(message);
      if (uploadMsg) uploadMsg.textContent = message;
    }
  }

  function updateUploadGate() {
    const unlocked = isUploadUnlocked();
    const locked = captchaState.enabled && !unlocked;

    if (dropzone) {
      dropzone.classList.toggle("is-locked", locked);
      dropzone.setAttribute("aria-disabled", locked ? "true" : "false");
      if (locked) {
        dropzone.setAttribute("aria-describedby", "drop-hint captcha-hint");
      } else {
        dropzone.setAttribute("aria-describedby", "drop-hint");
      }
    }

    if (fileInput) {
      // Must stay enabled when unlocked — disabled inputs ignore .click()
      fileInput.disabled = locked;
    }

    if (clearFileBtn) {
      clearFileBtn.disabled = false;
    }

    if (locked) {
      if (dropLabel) dropLabel.textContent = "请先完成上方人机验证";
      if (dropHint) dropHint.textContent = "验证通过后即可选择或拖入压缩包";
      if (uploadBadge && uploadBadge.dataset.state === "idle") {
        setUploadBadge("idle", "待验证");
      }
      if (uploadMsg && !state.uploading && !state.uploadId) {
        uploadMsg.textContent = "请先完成人机验证，再选择文件";
      }
    } else {
      // Captcha off, or captcha passed — restore normal upload copy
      if (dropLabel && !state.file) {
        dropLabel.textContent = captchaState.enabled
          ? "② 拖拽文件到这里，或点击选择"
          : "拖拽文件到这里，或点击选择";
      }
      if (dropHint && !state.file) {
        dropHint.textContent = "支持较大的检查压缩包";
      }
      if (uploadBadge && uploadBadge.dataset.state === "idle") {
        setUploadBadge("idle", "待上传");
      }
      if (uploadMsg && !state.uploading && !state.uploadId && !state.file) {
        uploadMsg.textContent = captchaState.enabled
          ? "验证已通过，请选择要转换的文件"
          : "请先选择要转换的文件";
      }
    }
  }

  function loadTurnstileScript() {
    if (window.turnstile) return Promise.resolve();
    if (captchaState.scriptLoading) return captchaState.scriptLoading;
    captchaState.scriptLoading = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
      s.async = true;
      s.defer = true;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error("人机验证脚本加载失败"));
      document.head.appendChild(s);
    });
    return captchaState.scriptLoading;
  }

  function onCaptchaToken(token) {
    captchaState.token = token || "";
    const hint = $("captcha-hint");
    if (hint) {
      hint.textContent = "验证通过，请选择文件上传";
      hint.classList.remove("is-error");
    }
    setError("");
    updateUploadGate();
  }

  function onCaptchaExpired() {
    captchaState.token = "";
    const hint = $("captcha-hint");
    if (hint) {
      hint.textContent = "验证已过期，请重新完成人机验证后再选择文件";
      hint.classList.add("is-error");
    }
    updateUploadGate();
  }

  function onCaptchaError(errorCode) {
    captchaState.token = "";
    const hint = $("captcha-hint");
    if (!hint) return;
    const host = location.hostname || "localhost";
    const code = errorCode != null ? String(errorCode) : "";
    // 110200 = domain not authorized (most common for local preview)
    if (code === "110200" || !code) {
      hint.textContent =
        `人机验证加载失败（${code || "网络/域名"}）。请在 Cloudflare Turnstile 控制台把「${host}」和 localhost、127.0.0.1 加入 Hostname Management，保存后强制刷新本页。`;
    } else {
      hint.textContent = `人机验证失败（错误码 ${code}）。可尝试关闭广告拦截、换网络后刷新。`;
    }
    hint.classList.add("is-error");
    updateUploadGate();
  }

  async function initCaptcha(siteKey) {
    captchaState.enabled = true;
    captchaState.siteKey = siteKey;
    captchaState.token = "";
    const wrap = $("captcha-wrap");
    const el = $("turnstile-widget");
    if (wrap) wrap.hidden = false;
    // Lock immediately so user cannot pick files before challenge finishes
    updateUploadGate();
    if (!el || !siteKey) return;
    try {
      await loadTurnstileScript();
      if (!window.turnstile) return;
      if (captchaState.widgetId != null) {
        try {
          window.turnstile.reset(captchaState.widgetId);
        } catch (_) {}
        updateUploadGate();
        return;
      }
      const theme = getTheme() === "dark" ? "dark" : "light";
      captchaState.widgetId = window.turnstile.render(el, {
        sitekey: siteKey,
        theme,
        action: "turnstile-spin-v2",
        callback: onCaptchaToken,
        "expired-callback": onCaptchaExpired,
        "error-callback": onCaptchaError,
      });
      updateUploadGate();
    } catch (e) {
      const hint = $("captcha-hint");
      if (hint) {
        hint.textContent = String(e.message || e);
        hint.classList.add("is-error");
      }
      updateUploadGate();
    }
  }

  function resetCaptcha() {
    captchaState.token = "";
    if (captchaState.widgetId != null && window.turnstile) {
      try {
        window.turnstile.reset(captchaState.widgetId);
      } catch (_) {}
    }
    updateUploadGate();
  }

  async function ensureAuth() {
    try {
      const res = await fetch("/api/v1/bootstrap");
      if (!res.ok) return;
      const data = await res.json();
      state.chunkedUploadEnabled = Boolean(data.chunked_upload_enabled);
      if (data.chunk_size_bytes && Number(data.chunk_size_bytes) > 0) {
        state.chunkSizeBytes = Number(data.chunk_size_bytes);
      }
      if (data.auth_required) {
        const existing = getToken();
        if (existing) {
          const ok = await verifyAccessToken(existing);
          if (!ok) {
            setToken("");
            await showAuthOverlay("密码不正确或已失效，请重新输入");
          }
        } else {
          await showAuthOverlay();
        }
      } else {
        // Auth disabled: drop any leftover session token
        setToken("");
      }
      if (data.captcha_enabled && data.captcha_site_key) {
        await initCaptcha(data.captcha_site_key);
      } else {
        captchaState.enabled = false;
        captchaState.token = "";
        captchaState.widgetId = null;
        const wrap = $("captcha-wrap");
        if (wrap) wrap.hidden = true;
        updateUploadGate();
      }
    } catch (_) {
      // Network failure: do not leave upload permanently locked
      captchaState.enabled = false;
      updateUploadGate();
    }
  }

  function parseApiError(status, body, textFallback) {
    let detail = "";
    let code = "";
    if (body && typeof body === "object") {
      detail = body.detail || body.message || "";
      code = body.code || "";
      if (typeof detail === "object" && detail) {
        code = detail.code || code;
        detail = detail.detail || detail.message || JSON.stringify(detail);
      }
    }
    if (!detail && textFallback) detail = String(textFallback).slice(0, 200);
    // Cloudflare / reverse-proxy friendly messages
    if (status === 413) {
      return {
        code: code || "PAYLOAD_TOO_LARGE",
        detail:
          detail && !/<html/i.test(detail)
            ? detail
            : "文件过大，被网关拒绝（例如 Cloudflare 约 100MB 限制）。请启用分片上传或缩小文件。",
      };
    }
    if (status === 524 || status === 504) {
      return {
        code: code || "GATEWAY_TIMEOUT",
        detail:
          "上传超时（Cloudflare 约 100 秒限制）。请把服务端 DICOMFLOW_CHUNK_SIZE_MB 设为 2 或 4，重启后再传；并强制刷新页面以免使用旧前端。",
      };
    }
    if (status === 502 || status === 503) {
      return {
        code: code || "BAD_GATEWAY",
        detail: detail && !/<html/i.test(detail)
          ? detail
          : "网关错误，上传中断。大文件请启用分片上传后重试。",
      };
    }
    return { code, detail: detail || `HTTP ${status}` };
  }

  async function apiFetch(url, options) {
    const opts = options || {};
    const headers = authHeaders(opts.headers || {});
    let res = await fetch(url, Object.assign({}, opts, { headers }));
    if (res.status === 401) {
      let code = "";
      try {
        const body = await res.clone().json();
        code = body.code || "";
      } catch (_) {}
      if (code === "AUTH_REQUIRED" || !code) {
        await showAuthOverlay("密码不正确，请重新输入");
        res = await fetch(url, Object.assign({}, opts, { headers: authHeaders(opts.headers || {}) }));
      }
    }
    return res;
  }

  const state = {
    file: null,
    uploadId: null,
    uploading: false,
    converting: false,
    jobId: null,
    pollTimer: null,
    outputFormat: null,
    /** From bootstrap: use multi-part when true (Cloudflare-friendly). */
    chunkedUploadEnabled: false,
    chunkSizeBytes: 4 * 1024 * 1024,
    /** Abort token for in-flight chunked upload */
    uploadGeneration: 0,
  };

  function formatBytes(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(1)} MB`;
  }

  function setBar(bar, wrap, pctEl, pct) {
    const v = Math.max(0, Math.min(100, Math.round(pct)));
    bar.style.width = `${v}%`;
    if (wrap) wrap.setAttribute("aria-valuenow", String(v));
    if (pctEl) pctEl.textContent = `${v}%`;
  }

  function setError(msg) {
    if (!msg) {
      errorBox.hidden = true;
      errorBox.textContent = "";
      return;
    }
    errorBox.hidden = false;
    errorBox.textContent = msg;
  }

  function setUploadBadge(stateName, text) {
    uploadBadge.dataset.state = stateName;
    uploadBadge.textContent = text;
  }

  function updateConvertEnabled() {
    const ready = Boolean(state.uploadId) && !state.uploading && !state.converting;
    convertBtn.disabled = !ready;
    convertBtn.classList.toggle("is-loading", state.converting);
    convertHint.textContent = state.converting
      ? "正在转换，请稍候…"
      : ready
        ? "已选好文件，可以开始转换"
        : state.uploading
          ? "上传完成后即可转换"
          : "请先上传文件";
  }

  function clearPreviewMedia() {
    previewVideo.pause();
    previewVideo.removeAttribute("src");
    previewVideo.load();
    previewVideo.hidden = true;
    previewImage.removeAttribute("src");
    previewImage.removeAttribute("alt");
    previewImage.hidden = true;
    previewEmpty.hidden = false;
    previewEmpty.textContent = "从右侧列表选择一条序列进行预览";
  }

  function selectFile(file) {
    if (!file) return;
    if (!isUploadUnlocked()) {
      // Reset input so the same file can be re-chosen after captcha
      if (fileInput) fileInput.value = "";
      focusCaptchaGate("请先完成人机验证，再选择文件");
      updateUploadGate();
      return;
    }
    state.file = file;
    state.uploadId = null;
    state.jobId = null;
    state.outputFormat = null;
    state.converting = false;
    if (state.pollTimer) {
      clearTimeout(state.pollTimer);
      state.pollTimer = null;
    }

    fileChip.hidden = false;
    fileNameEl.textContent = file.name;
    fileSizeEl.textContent = formatBytes(file.size);
    dropLabel.textContent = "可重新选择其他文件";
    resultPanel.hidden = true;
    clearPreviewMedia();
    setError("");
    setBar(processBar, processWrap, processPct, 0);
    processMsg.textContent = "上传完成后即可开始";
    processMeta.hidden = true;
    setBar(uploadBar, uploadWrap, uploadPct, 0);
    setUploadBadge("uploading", "上传中");
    updateConvertEnabled();
    startUpload(file);
  }

  function startUpload(file) {
    if (!isUploadUnlocked()) {
      state.uploading = false;
      setUploadBadge("idle", "待验证");
      updateConvertEnabled();
      focusCaptchaGate("请先完成人机验证，再上传");
      updateUploadGate();
      return;
    }

    state.uploading = true;
    state.uploadGeneration += 1;
    const gen = state.uploadGeneration;
    updateConvertEnabled();
    uploadMsg.textContent = "正在上传文件…";
    setError("");

    if (state.chunkedUploadEnabled) {
      startChunkedUpload(file, gen);
      return;
    }
    startSingleUpload(file, gen);
  }

  function startSingleUpload(file, gen) {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/v1/uploads");
    xhr.responseType = "json";
    xhr.timeout = 0;
    const tok = getToken();
    if (tok) xhr.setRequestHeader("X-DicomFlow-Token", tok);

    xhr.upload.onprogress = (e) => {
      if (gen !== state.uploadGeneration) return;
      if (!e.lengthComputable) {
        uploadMsg.textContent = "正在上传文件…";
        return;
      }
      const pct = (e.loaded / e.total) * 100;
      setBar(uploadBar, uploadWrap, uploadPct, pct);
      uploadMsg.textContent = `上传中 ${formatBytes(e.loaded)} / ${formatBytes(e.total)}`;
    };

    xhr.onload = async () => {
      if (gen !== state.uploadGeneration) return;
      if (xhr.status === 401) {
        state.uploading = false;
        try {
          await showAuthOverlay("请先输入访问密码");
          startUpload(file);
        } catch (_) {
          setUploadBadge("error", "未通过验证");
          uploadMsg.textContent = "未通过验证";
          updateConvertEnabled();
        }
        return;
      }
      state.uploading = false;
      if (xhr.status >= 200 && xhr.status < 300 && xhr.response?.upload_id) {
        onUploadSuccess(xhr.response, file);
        return;
      }
      let body = typeof xhr.response === "object" ? xhr.response : null;
      if (!body && xhr.responseText) {
        try {
          body = JSON.parse(xhr.responseText);
        } catch (_) {
          body = null;
        }
      }
      const parsed = parseApiError(xhr.status, body, xhr.responseText || xhr.statusText);
      if (String(parsed.code).startsWith("CAPTCHA") || xhr.status === 400) {
        resetCaptcha();
      }
      setUploadBadge("error", "失败");
      uploadMsg.textContent = String(parsed.code).startsWith("CAPTCHA")
        ? "人机验证未通过，请重试"
        : "上传失败，请重试";
      setError(`上传失败：${parsed.detail || "请检查文件后重试"}`);
      updateConvertEnabled();
    };

    xhr.onerror = () => {
      if (gen !== state.uploadGeneration) return;
      state.uploading = false;
      setUploadBadge("error", "失败");
      uploadMsg.textContent = "网络异常，请重试";
      setError("网络异常，上传失败，请检查网络后重试");
      updateConvertEnabled();
    };

    const body = new FormData();
    body.append("file", file);
    const captchaTok = getCaptchaToken();
    if (captchaTok) {
      body.append("cf-turnstile-response", captchaTok);
    }
    xhr.send(body);
  }

  function onUploadSuccess(data, file) {
    state.uploadId = data.upload_id;
    setBar(uploadBar, uploadWrap, uploadPct, 100);
    setUploadBadge("ready", "已完成");
    uploadMsg.textContent = `上传成功：${data.filename || file.name}（${formatBytes(
      data.size_bytes || file.size
    )}）`;
    resetCaptcha();
    updateConvertEnabled();
  }

  /**
   * Multi-part upload: init → POST parts → complete.
   * Part size comes from bootstrap (default 4MB) to finish each request under CF ~100s.
   */
  async function startChunkedUpload(file, gen) {
    const chunkSize = Math.max(64 * 1024, state.chunkSizeBytes || 8 * 1024 * 1024);
    const totalChunks = Math.max(1, Math.ceil(file.size / chunkSize));

    const fail = (msg, opts) => {
      if (gen !== state.uploadGeneration) return;
      state.uploading = false;
      setUploadBadge("error", "失败");
      uploadMsg.textContent = (opts && opts.badge) || "上传失败，请重试";
      setError(`上传失败：${msg || "请检查文件后重试"}`);
      if (opts && opts.resetCaptcha) resetCaptcha();
      updateConvertEnabled();
    };

    try {
      uploadMsg.textContent = `准备分片上传（共 ${totalChunks} 片）…`;
      const initPayload = {
        filename: file.name,
        size_bytes: file.size,
      };
      const captchaTok = getCaptchaToken();
      if (captchaTok) initPayload.captcha_token = captchaTok;

      const initHeaders = authHeaders({ "Content-Type": "application/json" });
      if (captchaTok) {
        initHeaders["cf-turnstile-response"] = captchaTok;
        initHeaders["x-turnstile-token"] = captchaTok;
      }

      let initRes = await fetch("/api/v1/uploads/init", {
        method: "POST",
        headers: initHeaders,
        body: JSON.stringify(initPayload),
      });
      if (initRes.status === 401) {
        await showAuthOverlay("请先输入访问密码");
        if (gen !== state.uploadGeneration) return;
        initRes = await fetch("/api/v1/uploads/init", {
          method: "POST",
          headers: authHeaders({
            "Content-Type": "application/json",
            ...(captchaTok
              ? {
                  "cf-turnstile-response": captchaTok,
                  "x-turnstile-token": captchaTok,
                }
              : {}),
          }),
          body: JSON.stringify(initPayload),
        });
      }
      if (gen !== state.uploadGeneration) return;

      if (!initRes.ok) {
        let body = null;
        const text = await initRes.text();
        try {
          body = JSON.parse(text);
        } catch (_) {}
        const parsed = parseApiError(initRes.status, body, text);
        if (String(parsed.code).startsWith("CAPTCHA")) {
          fail(parsed.detail, { badge: "人机验证未通过，请重试", resetCaptcha: true });
        } else {
          fail(parsed.detail, { resetCaptcha: initRes.status === 400 });
        }
        return;
      }

      const session = await initRes.json();
      const uploadId = session.upload_id;
      const serverChunk = session.chunk_size_bytes || chunkSize;
      const serverTotal = session.total_chunks || totalChunks;
      let uploadedBytes = 0;

      const paintProgress = (loadedInPart, partIndex) => {
        if (gen !== state.uploadGeneration) return;
        const overall = Math.min(file.size, uploadedBytes + (loadedInPart || 0));
        const pct = file.size ? (overall / file.size) * 100 : 0;
        setBar(uploadBar, uploadWrap, uploadPct, pct);
        uploadMsg.textContent = `分片上传 ${partIndex + 1}/${serverTotal} · ${formatBytes(
          overall
        )} / ${formatBytes(file.size)}`;
      };

      for (let i = 0; i < serverTotal; i++) {
        if (gen !== state.uploadGeneration) return;
        const start = i * serverChunk;
        const end = Math.min(file.size, start + serverChunk);
        const blob = file.slice(start, end);
        // Show next part immediately so the bar never looks "stuck" between requests
        paintProgress(0, i);

        const partOk = await putChunkWithRetry(uploadId, i, blob, {
          gen,
          onProgress: (loaded) => paintProgress(loaded, i),
        });
        if (!partOk.ok) {
          fail(partOk.detail || `第 ${i + 1} 片上传失败`);
          return;
        }
        uploadedBytes += blob.size;
        paintProgress(0, i); // snap to completed part boundary
      }

      if (gen !== state.uploadGeneration) return;
      uploadMsg.textContent = "正在合并分片…";
      const doneRes = await apiFetch(`/api/v1/uploads/${uploadId}/complete`, {
        method: "POST",
      });
      if (gen !== state.uploadGeneration) return;
      if (!doneRes.ok) {
        let body = null;
        const text = await doneRes.text();
        try {
          body = JSON.parse(text);
        } catch (_) {}
        const parsed = parseApiError(doneRes.status, body, text);
        fail(parsed.detail || "合并分片失败");
        return;
      }
      const data = await doneRes.json();
      state.uploading = false;
      onUploadSuccess(data, file);
    } catch (e) {
      if (gen !== state.uploadGeneration) return;
      fail(e && e.message ? e.message : String(e));
    }
  }

  function putChunkWithRetry(uploadId, index, blob, { gen, onProgress, maxAttempts }) {
    const attempts = maxAttempts || 3;
    // Per-part budget: large enough for slow links, short enough to fail before CF 100s
    // feels like a silent hang. ~3 min; retries handle transient 502/524.
    const partTimeoutMs = 180000;
    return new Promise((resolve) => {
      let attempt = 0;
      const run = () => {
        if (gen !== state.uploadGeneration) {
          resolve({ ok: false, detail: "已取消" });
          return;
        }
        attempt += 1;
        const xhr = new XMLHttpRequest();
        // POST is more reliably handled by reverse proxies than PUT for large bodies
        xhr.open("POST", `/api/v1/uploads/${uploadId}/chunks/${index}`);
        xhr.responseType = "text";
        xhr.timeout = partTimeoutMs;
        const tok = getToken();
        if (tok) xhr.setRequestHeader("X-DicomFlow-Token", tok);
        xhr.setRequestHeader("Content-Type", "application/octet-stream");

        xhr.upload.onprogress = (e) => {
          if (onProgress) {
            if (e.lengthComputable) onProgress(e.loaded);
            else if (e.loaded) onProgress(e.loaded);
          }
        };

        const parseBody = () => {
          if (!xhr.responseText) return null;
          try {
            return JSON.parse(xhr.responseText);
          } catch (_) {
            return null;
          }
        };

        xhr.onload = () => {
          if (gen !== state.uploadGeneration) {
            resolve({ ok: false, detail: "已取消" });
            return;
          }
          if (xhr.status >= 200 && xhr.status < 300) {
            if (onProgress) onProgress(blob.size);
            resolve({ ok: true });
            return;
          }
          if (xhr.status === 401 && attempt < attempts) {
            showAuthOverlay("请先输入访问密码")
              .then(() => run())
              .catch(() => resolve({ ok: false, detail: "未通过验证" }));
            return;
          }
          // Retry transient gateway errors
          if (
            (xhr.status === 502 || xhr.status === 503 || xhr.status === 524 || xhr.status === 408) &&
            attempt < attempts
          ) {
            setTimeout(run, 800 * attempt);
            return;
          }
          const body = parseBody();
          const parsed = parseApiError(xhr.status, body, xhr.responseText || xhr.statusText);
          resolve({
            ok: false,
            detail: parsed.detail || `第 ${index + 1} 片失败 (HTTP ${xhr.status})`,
          });
        };

        xhr.onerror = () => {
          if (gen !== state.uploadGeneration) {
            resolve({ ok: false, detail: "已取消" });
            return;
          }
          if (attempt < attempts) {
            setTimeout(run, 800 * attempt);
            return;
          }
          resolve({ ok: false, detail: "网络异常，分片上传失败" });
        };

        xhr.ontimeout = () => {
          if (gen !== state.uploadGeneration) {
            resolve({ ok: false, detail: "已取消" });
            return;
          }
          if (attempt < attempts) {
            setTimeout(run, 800 * attempt);
            return;
          }
          resolve({
            ok: false,
            detail: `第 ${index + 1} 片上传超时，请检查网络后重试`,
          });
        };

        xhr.send(blob);
      };
      run();
    });
  }

  async function startConvert() {
    if (!state.uploadId || state.converting) return;
    setError("");
    resultPanel.hidden = true;
    clearPreviewMedia();
    state.converting = true;
    updateConvertEnabled();
    setBar(processBar, processWrap, processPct, 0);
    processMsg.textContent = "正在开始转换…";
    processMeta.hidden = true;

    const fmt = $("format").value;
    state.outputFormat = fmt === "gif" ? "gif" : "mp4";

    const payload = {
      upload_id: state.uploadId,
      format: state.outputFormat,
      quality: $("quality").value,
      merge: $("merge").checked,
      fps: Number($("fps").value) || 10,
    };

    try {
      const res = await apiFetch("/api/v1/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let msg = "转换启动失败，请稍后重试";
        try {
          const body = await res.json();
          msg = body.detail || body.message || msg;
          if (typeof msg === "object") msg = JSON.stringify(msg);
        } catch (_) {}
        throw new Error(msg);
      }
      const data = await res.json();
      state.jobId = data.job_id;
      processMsg.textContent = "已开始转换…";
      // Sequential poll (not setInterval) avoids stacking requests and 429 storms
      if (state.pollTimer) {
        clearTimeout(state.pollTimer);
        state.pollTimer = null;
      }
      await runJobPollLoop(data.job_id);
    } catch (e) {
      setError(String(e));
      processMsg.textContent = "转换未能开始，请重试";
      state.converting = false;
      updateConvertEnabled();
    }
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  /**
   * Poll job status until terminal or cancelled.
   * 429 is retried with backoff — conversion continues server-side.
   */
  async function runJobPollLoop(jobId) {
    const pollEveryMs = 2000;
    let rateLimitHits = 0;
    while (state.converting && state.jobId === jobId) {
      try {
        const terminal = await pollJob(jobId);
        rateLimitHits = 0;
        if (terminal) return;
        await sleep(pollEveryMs);
      } catch (e) {
        const msg = String(e && e.message ? e.message : e);
        if (msg.includes("RATE_LIMITED") || msg.includes("429") || msg.includes("过于频繁")) {
          rateLimitHits += 1;
          const wait = Math.min(10000, 1500 * rateLimitHits);
          processMsg.textContent = "查询进度稍频，稍后继续…";
          await sleep(wait);
          continue;
        }
        setError(msg);
        state.converting = false;
        state.pollTimer = null;
        updateConvertEnabled();
        return;
      }
    }
  }

  /** @returns {Promise<boolean>} true if job reached a terminal status */
  async function pollJob(jobId) {
    const res = await apiFetch(`/api/v1/jobs/${jobId}`);
    if (res.status === 429) {
      const err = new Error("RATE_LIMITED");
      err.code = "RATE_LIMITED";
      throw err;
    }
    if (!res.ok) throw new Error("获取进度失败，请刷新后重试");
    const data = await res.json();
    const pct = data.progress?.percent ?? 0;
    setBar(processBar, processWrap, processPct, pct);

    const statusLabel =
      {
        PENDING: "排队中",
        RUNNING: "转换中",
        SUCCEEDED: "已完成",
        FAILED: "失败",
      }[data.status] || data.status;

    const phaseMsg = data.progress?.message || "";
    processMsg.textContent = phaseMsg ? `${statusLabel}：${phaseMsg}` : statusLabel;

    if (data.progress?.series_total) {
      processMeta.hidden = false;
      const fi = data.progress.frame_index;
      const ft = data.progress.frame_total;
      const frameBit = fi != null && ft != null ? `，第 ${fi}/${ft} 帧` : "";
      processMeta.textContent = `正在处理第 ${data.progress.series_index || "—"} / ${data.progress.series_total} 个序列${frameBit}`;
    }

    if (data.status === "SUCCEEDED") {
      state.pollTimer = null;
      state.converting = false;
      setBar(processBar, processWrap, processPct, 100);
      processMsg.textContent = "转换完成，可以预览或下载";
      updateConvertEnabled();
      showResults(jobId, data.result);
      return true;
    }

    if (data.status === "FAILED") {
      state.pollTimer = null;
      state.converting = false;
      updateConvertEnabled();
      const err = data.error;
      const msg = err?.message || "转换失败，请检查文件后重试";
      const detail = err?.detail ? `\n${err.detail}` : "";
      setError(`${msg}${detail}`);
      processMsg.textContent = "转换失败";
      return true;
    }
    return false;
  }

  function isPreviewableForFormat(name, format) {
    const lower = name.toLowerCase();
    if (format === "gif") return lower.endsWith(".gif");
    return lower.endsWith(".mp4") || lower.endsWith(".webm");
  }

  function kindLabel(kind) {
    return { series: "序列", merged: "合并", zip: "压缩包", result: "结果" }[kind] || kind || "";
  }

  function showResults(jobId, result) {
    if (!result) return;
    resultPanel.hidden = false;
    clearPreviewMedia();

    downloadBtn.onclick = () => {
      // Use fetch+blob so access token header can be attached
      apiFetch(`/api/v1/jobs/${jobId}/download`)
        .then(async (res) => {
          if (!res.ok) throw new Error("下载失败，请稍后重试");
          const blob = await res.blob();
          const cd = res.headers.get("content-disposition") || "";
          let name = "download.bin";
          const m = /filename="?([^";]+)"?/i.exec(cd);
          if (m) name = m[1];
          else if (result.download_name) name = result.download_name;
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = name;
          a.click();
          URL.revokeObjectURL(a.href);
        })
        .catch((e) => setError(String(e)));
    };

    const format = state.outputFormat || "mp4";
    const outputs = (result.outputs || []).filter(
      (o) => o.previewable && isPreviewableForFormat(o.name, format)
    );

    const listItems =
      outputs.length > 0
        ? outputs
        : result.download_name && isPreviewableForFormat(result.download_name, format)
          ? [
              {
                name: result.download_name,
                kind: "result",
                size_bytes: result.size_bytes,
                previewable: true,
              },
            ]
          : [];

    fileList.innerHTML = "";
    if (!listItems.length) {
      previewEmpty.hidden = false;
      previewEmpty.textContent = "暂无可预览内容，请直接下载结果";
      resultPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }

    listItems.forEach((item) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "file-item";
      btn.setAttribute("role", "option");
      btn.setAttribute("aria-selected", "false");
      btn.dataset.name = item.name;
      btn.innerHTML = `
        <span class="file-item-name">${escapeHtml(item.name)}</span>
        <span class="file-item-meta">${escapeHtml(kindLabel(item.kind))}${
        item.size_bytes != null ? " · " + formatBytes(item.size_bytes) : ""
      }</span>
      `;
      btn.addEventListener("click", () => selectPreview(jobId, item, btn, format));
      li.appendChild(btn);
      fileList.appendChild(li);
    });

    const preferred = listItems.find((o) => o.kind === "merged") || listItems[0];
    const preferredBtn = [...fileList.querySelectorAll(".file-item")].find(
      (b) => b.dataset.name === preferred.name
    );
    if (preferredBtn) selectPreview(jobId, preferred, preferredBtn, format);

    resultPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function selectPreview(jobId, item, btn, format) {
    fileList.querySelectorAll(".file-item").forEach((el) => {
      el.setAttribute("aria-selected", el === btn ? "true" : "false");
    });

    clearPreviewMedia();
    previewEmpty.hidden = true;

    const url = `/api/v1/jobs/${jobId}/files/${encodeURIComponent(item.name)}`;
    const lower = item.name.toLowerCase();
    const useGif = format === "gif" || lower.endsWith(".gif");

    // Fetch with token then blob URL (media tags cannot send custom headers)
    apiFetch(url)
      .then(async (res) => {
        if (!res.ok) throw new Error("预览加载失败，请稍后重试");
        const blob = await res.blob();
        const blobUrl = URL.createObjectURL(blob);
        if (useGif) {
          previewImage.hidden = false;
          previewImage.alt = `预览 ${item.name}`;
          previewImage.onload = () => URL.revokeObjectURL(blobUrl);
          previewImage.src = blobUrl;
        } else {
          previewVideo.hidden = false;
          previewVideo.onloadeddata = () => {
            /* keep blob until new preview */
          };
          previewVideo.src = blobUrl;
          previewVideo.load();
        }
      })
      .catch((e) => {
        previewEmpty.hidden = false;
        previewEmpty.textContent = String(e);
        setError(String(e));
      });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function openFilePicker() {
    if (!isUploadUnlocked()) {
      focusCaptchaGate("请先完成人机验证，再选择文件");
      updateUploadGate();
      return;
    }
    if (!fileInput || fileInput.disabled) {
      updateUploadGate();
      if (fileInput) fileInput.disabled = false;
    }
    // Nested <input type=file> click can bubble back to dropzone; stop that
    fileInput.click();
  }

  // Prevent re-entrancy: programmatic fileInput.click() must not re-trigger dropzone
  fileInput?.addEventListener("click", (e) => {
    e.stopPropagation();
  });

  dropzone.addEventListener("click", (e) => {
    if (e.target === fileInput || fileInput?.contains?.(e.target)) return;
    openFilePicker();
  });
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openFilePicker();
    }
  });
  ["dragenter", "dragover"].forEach((ev) => {
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      if (!isUploadUnlocked()) {
        dropzone.classList.remove("dragover");
        return;
      }
      dropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((ev) => {
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    });
  });
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    if (!isUploadUnlocked()) {
      focusCaptchaGate("请先完成人机验证，再拖入文件");
      updateUploadGate();
      return;
    }
    const file = e.dataTransfer.files?.[0];
    if (file) selectFile(file);
  });
  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (file) selectFile(file);
  });
  clearFileBtn.addEventListener("click", () => {
    state.uploadGeneration += 1; // cancel in-flight upload
    state.file = null;
    state.uploadId = null;
    state.uploading = false;
    state.outputFormat = null;
    state.converting = false;
    fileInput.value = "";
    fileChip.hidden = true;
    setBar(uploadBar, uploadWrap, uploadPct, 0);
    setUploadBadge("idle", "待上传");
    uploadMsg.textContent = "请先选择要转换的文件";
    resultPanel.hidden = true;
    clearPreviewMedia();
    setError("");
    updateConvertEnabled();
    updateUploadGate();
  });
  convertBtn.addEventListener("click", startConvert);
  updateConvertEnabled();
  // Bootstrap auth + captcha after UI hooks are ready (gates dropzone when captcha on)
  ensureAuth();
})();
