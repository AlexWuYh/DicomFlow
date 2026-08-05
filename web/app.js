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
      input.value = getToken();
      setTimeout(() => input.focus(), 50);
    }
    return new Promise((resolve) => {
      const submit = $("auth-submit");
      const onSubmit = () => {
        const v = (input && input.value ? input.value : "").trim();
        if (!v) {
          if (err) {
            err.hidden = false;
            err.textContent = "请输入访问密码";
          }
          return;
        }
        setToken(v);
        overlay.hidden = true;
        submit?.removeEventListener("click", onSubmit);
        input?.removeEventListener("keydown", onKey);
        resolve(v);
      };
      const onKey = (e) => {
        if (e.key === "Enter") onSubmit();
      };
      submit?.addEventListener("click", onSubmit);
      input?.addEventListener("keydown", onKey);
    });
  }

  async function ensureAuth() {
    try {
      const res = await fetch("/api/v1/bootstrap");
      if (!res.ok) return;
      const data = await res.json();
      if (data.auth_required && !getToken()) {
        await showAuthOverlay();
      }
    } catch (_) {}
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

  ensureAuth();

  const dropzone = $("dropzone");
  const fileInput = $("file-input");
  const dropLabel = $("drop-label");
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

  const state = {
    file: null,
    uploadId: null,
    uploading: false,
    converting: false,
    jobId: null,
    pollTimer: null,
    outputFormat: null,
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
    state.file = file;
    state.uploadId = null;
    state.jobId = null;
    state.outputFormat = null;
    state.converting = false;
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
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
    state.uploading = true;
    updateConvertEnabled();
    uploadMsg.textContent = "正在上传文件…";

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/v1/uploads");
    xhr.responseType = "json";
    xhr.timeout = 0;
    const tok = getToken();
    if (tok) xhr.setRequestHeader("X-DicomFlow-Token", tok);

    xhr.upload.onprogress = (e) => {
      if (!e.lengthComputable) {
        uploadMsg.textContent = "正在上传文件…";
        return;
      }
      const pct = (e.loaded / e.total) * 100;
      setBar(uploadBar, uploadWrap, uploadPct, pct);
      uploadMsg.textContent = `上传中 ${formatBytes(e.loaded)} / ${formatBytes(e.total)}`;
    };

    xhr.onload = async () => {
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
        state.uploadId = xhr.response.upload_id;
        setBar(uploadBar, uploadWrap, uploadPct, 100);
        setUploadBadge("ready", "已完成");
        uploadMsg.textContent = `上传成功：${xhr.response.filename || file.name}（${formatBytes(
          xhr.response.size_bytes || file.size
        )}）`;
        updateConvertEnabled();
        return;
      }
      let detail = "";
      try {
        const body = typeof xhr.response === "object" ? xhr.response : null;
        detail = body?.detail || body?.message || xhr.responseText || xhr.statusText;
        if (typeof detail === "object") detail = JSON.stringify(detail);
      } catch {
        detail = xhr.statusText;
      }
      setUploadBadge("error", "失败");
      uploadMsg.textContent = "上传失败，请重试";
      setError(`上传失败：${detail || "请检查文件后重试"}`);
      updateConvertEnabled();
    };

    xhr.onerror = () => {
      state.uploading = false;
      setUploadBadge("error", "失败");
      uploadMsg.textContent = "网络异常，请重试";
      setError("网络异常，上传失败，请检查网络后重试");
      updateConvertEnabled();
    };

    const body = new FormData();
    body.append("file", file);
    xhr.send(body);
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
      if (state.pollTimer) clearInterval(state.pollTimer);
      state.pollTimer = setInterval(() => {
        pollJob(state.jobId).catch((e) => {
          setError(String(e));
          clearInterval(state.pollTimer);
          state.pollTimer = null;
          state.converting = false;
          updateConvertEnabled();
        });
      }, 1000);
      await pollJob(state.jobId);
    } catch (e) {
      setError(String(e));
      processMsg.textContent = "转换未能开始，请重试";
      state.converting = false;
      updateConvertEnabled();
    }
  }

  async function pollJob(jobId) {
    const res = await apiFetch(`/api/v1/jobs/${jobId}`);
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
      if (state.pollTimer) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
      }
      state.converting = false;
      setBar(processBar, processWrap, processPct, 100);
      processMsg.textContent = "转换完成，可以预览或下载";
      updateConvertEnabled();
      showResults(jobId, data.result);
      return;
    }

    if (data.status === "FAILED") {
      if (state.pollTimer) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
      }
      state.converting = false;
      updateConvertEnabled();
      const err = data.error;
      const msg = err?.message || "转换失败，请检查文件后重试";
      const detail = err?.detail ? `\n${err.detail}` : "";
      setError(`${msg}${detail}`);
      processMsg.textContent = "转换失败";
    }
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

  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });
  ["dragenter", "dragover"].forEach((ev) => {
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
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
    const file = e.dataTransfer.files?.[0];
    if (file) selectFile(file);
  });
  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (file) selectFile(file);
  });
  clearFileBtn.addEventListener("click", () => {
    state.file = null;
    state.uploadId = null;
    state.outputFormat = null;
    state.converting = false;
    fileInput.value = "";
    fileChip.hidden = true;
    dropLabel.textContent = "拖拽文件到这里，或点击选择";
    setBar(uploadBar, uploadWrap, uploadPct, 0);
    uploadMsg.textContent = "请先选择要转换的文件";
    setUploadBadge("idle", "待上传");
    resultPanel.hidden = true;
    clearPreviewMedia();
    updateConvertEnabled();
  });
  convertBtn.addEventListener("click", startConvert);
  updateConvertEnabled();
})();
