/* Universal Media Downloader — UI tĩnh, gọi thẳng API backend cùng origin.
   Không dùng dữ liệu giả: mọi số liệu/progress đến từ /api và SSE /api/events. */
"use strict";

const API = ""; // cùng origin (http://127.0.0.1:8756)

/* ------------------------------- i18n ---------------------------------- */
const I18N = {
  vi: {
    home: "Trang chủ", downloader: "Tải theo URL", batch: "Tải hàng loạt",
    queue: "Hàng đợi", history: "Lịch sử", settings: "Cài đặt",
    platforms: "Nền tảng", about: "Giới thiệu", analyze: "Phân tích",
    paste: "Dán", download: "Tải xuống", cancel: "Hủy", pause: "Tạm dừng",
    resume: "Tiếp tục", retry: "Thử lại", remove: "Xóa", reveal: "Mở thư mục",
    delete_hist: "Xóa khỏi lịch sử", best: "(chất lượng tốt nhất khả dụng)",
    connecting: "đang kết nối…", online: "Backend trực tuyến", offline: "MẤT KẾT NỐI backend",
    no_formats: "Nguồn không trả về danh sách định dạng.",
    pick_fmt: "Chọn định dạng bên dưới rồi bấm Tải xuống.",
    added: "Đã thêm vào hàng đợi.", started: "Bắt đầu tải…",
    err_network: "Không gọi được backend. Kiểm tra uvicorn còn chạy không.",
    tasks_total: "Tác vụ", completed: "Hoàn thành", failed_c: "Lỗi",
  },
  en: {
    home: "Home", downloader: "URL Downloader", batch: "Batch Download",
    queue: "Queue", history: "History", settings: "Settings",
    platforms: "Platforms", about: "About", analyze: "Analyze",
    paste: "Paste", download: "Download", cancel: "Cancel", pause: "Pause",
    resume: "Resume", retry: "Retry", remove: "Remove", reveal: "Open folder",
    delete_hist: "Delete from history", best: "(best available quality)",
    connecting: "connecting…", online: "Backend online", offline: "Backend OFFLINE",
    no_formats: "Source returned no format list.",
    pick_fmt: "Pick a format below, then press Download.",
    added: "Added to queue.", started: "Downloading…",
    err_network: "Cannot reach backend. Check that uvicorn is still running.",
    tasks_total: "Tasks", completed: "Completed", failed_c: "Failed",
  },
};
let LANG = localStorage.getItem("umd-lang") || "vi";
const t = (k) => (I18N[LANG][k] ?? k);

/* ------------------------------ helpers -------------------------------- */
const $ = (s) => document.querySelector(s);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const fmtBytes = (n) => { if (n == null) return "?"; const u = ["B","KB","MB","GB","TB"]; let i = 0; while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; } return n.toFixed(i ? 1 : 0) + " " + u[i]; };
const fmtDur = (s) => { if (s == null) return ""; s = Math.round(s); const h = Math.floor(s/3600), m = Math.floor(s%3600/60), sec = s%60; return (h ? h + ":" : "") + String(m).padStart(2,"0") + ":" + String(sec).padStart(2,"0"); };
const esc = (x) => String(x ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  try {
    const r = await fetch(API + "/api" + path, { headers: { "Content-Type": "application/json" }, ...opts });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const d = data.detail || {};
      const msg = typeof d === "string" ? d : (d.message_vi || d.message || r.statusText);
      const hint = typeof d === "object" ? d.hint_vi : "";
      throw new Error(msg + (hint ? " — " + hint : ""));
    }
    return data;
  } catch (e) {
    if (e instanceof TypeError) throw new Error(t("err_network"));
    throw e;
  }
}

function msg(box, text, kind = "info") {
  const b = typeof box === "string" ? $(box) : box;
  b.innerHTML = ""; b.appendChild(el("div", "msgline " + kind, esc(text)));
}
function clearMsg(box) { (typeof box === "string" ? $(box) : box).innerHTML = ""; }

/* ------------------------------ routing -------------------------------- */
const TITLES = { home: "home", downloader: "downloader", batch: "batch", queue: "queue", history: "history", settings: "settings", platforms: "platforms", about: "about" };
function showView(v) {
  document.querySelectorAll(".view").forEach(s => s.classList.remove("active"));
  $("#v-" + v).classList.add("active");
  document.querySelectorAll("#nav button").forEach(b => b.classList.toggle("active", b.dataset.view === v));
  $("#view-title").textContent = t(TITLES[v]);
  if (v === "queue") refreshQueue();
  if (v === "history") refreshHistory();
  if (v === "settings") refreshSettings();
  if (v === "platforms") refreshPlatforms();
  if (v === "home") refreshHomeStats();
}
$("#nav").addEventListener("click", e => { const b = e.target.closest("button[data-view]"); if (b) showView(b.dataset.view); });

/* theme + lang */
function applyTheme() { document.documentElement.dataset.theme = localStorage.getItem("umd-theme") || "dark"; }
$("#btn-theme").onclick = () => { localStorage.setItem("umd-theme", (document.documentElement.dataset.theme === "dark" ? "light" : "dark")); applyTheme(); };
$("#btn-lang").onclick = () => { LANG = LANG === "vi" ? "en" : "vi"; localStorage.setItem("umd-lang", LANG); applyLang(); };
function applyLang() {
  document.querySelectorAll("#nav button[data-view]").forEach(b => {
    const span = b.querySelector("span"); if (span) span.textContent = t(TITLES[b.dataset.view]);
  });
  $("#dl-analyze").textContent = t("analyze"); $("#home-analyze").textContent = t("analyze");
  $("#dl-paste").textContent = "📋 " + t("paste"); $("#home-paste").textContent = "📋 " + t("paste");
  ping().then(fillAbout);
}

/* --------------------------- connection state --------------------------- */
let healthCache = null;
async function ping() {
  try {
    healthCache = await api("/health");
    $("#conn-dot").className = "dot on"; $("#conn-text").textContent = t("online");
    return true;
  } catch {
    $("#conn-dot").className = "dot off"; $("#conn-text").textContent = t("offline");
    return false;
  }
}
setInterval(ping, 10000);

/* ------------------------------- clipboard ------------------------------ */
async function pasteInto(inputSel) {
  try {
    const txt = (await navigator.clipboard.readText()).trim();
    if (txt) $(inputSel).value = txt; else msg("#home-msg", "Clipboard rỗng.", "info");
  } catch { msg("#home-msg", "Trình duyệt chặn clipboard — hãy Ctrl+V vào ô nhập.", "info"); }
}
$("#home-paste").onclick = () => pasteInto("#home-url");
$("#dl-paste").onclick = () => pasteInto("#dl-url");

/* ============================ DOWNLOADER FLOW ============================ */
let currentMeta = null;   // metadata đang xem
let currentTaskId = null; // task đang tải từ trang này
let evtSource = null;

async function doAnalyze(urlInput) {
  const url = $(urlInput).value.trim();
  if (!url) return;
  clearMsg("#home-msg");
  if (urlInput === "#home-url") { switchToDownloader(url); return; }
  $("#dl-detect").innerHTML = '<span class="chip">đang nhận diện…</span>';
  hide(["#dl-preview", "#dl-formats", "#dl-task"]);
  try {
    const det = await api("/detect", { method: "POST", body: JSON.stringify({ url }) });
    renderDetect(det);
    const meta = await api("/analyze", { method: "POST", body: JSON.stringify({ url }) });
    currentMeta = meta;
    renderPreview(meta);
    renderFormats(meta);
  } catch (e) {
    $("#dl-detect").innerHTML = "";
    msg("#dl-detect", e.message, "err");
  }
}
function switchToDownloader(url) { showView("downloader"); $("#dl-url").value = url; doAnalyze("#dl-url"); }
$("#home-analyze").onclick = () => doAnalyze("#home-url");
$("#dl-analyze").onclick = () => doAnalyze("#dl-url");
for (const sel of ["#home-url", "#dl-url"]) $(sel).addEventListener("keydown", e => { if (e.key === "Enter") doAnalyze(sel); });

function statusChip(st) {
  const map = { supported: "ok", limited: "warn", "official-only": "warn", unsupported: "err", "needs-authentication": "warn" };
  return `<span class="chip ${map[st] || ""}">${esc(st)}</span>`;
}
function renderDetect(d) {
  $("#dl-detect").innerHTML =
    `<span class="chip">${esc(d.platform_display_name || "generic/unknown")}</span>` +
    (d.status ? statusChip(d.status) : "") + `<span class="chip">${esc(d.message_vi || "")}</span>`;
}
function hide(sels) { sels.forEach(s => $(s).classList.add("hidden")); }

function renderPreview(m) {
  const p = $("#dl-preview");
  p.innerHTML = `
    ${m.thumbnail ? `<img src="${esc(m.thumbnail)}" alt="thumbnail" referrerpolicy="no-referrer">` : ""}
    <div class="meta">
      <h3>${esc(m.title || "(không có tiêu đề)")}</h3>
      <p class="muted">${esc(m.uploader || "")} ${m.duration != null ? "· " + fmtDur(m.duration) : ""} ${m.is_live ? "· LIVE" : ""}</p>
      <p class="muted">${esc(m.platform_key)}${m.requires_auth ? " · cần đăng nhập/cookie được phép" : ""}</p>
    </div>`;
  p.classList.remove("hidden");
}

function renderFormats(m) {
  const box = $("#dl-formats");
  if (!m.formats || !m.formats.length) {
    box.innerHTML = `<h3>Định dạng</h3><p class="muted">${t("no_formats")} ${t("pick_fmt")}</p>
      <button class="btn primary" id="fmt-best">${t("download")} ${t("best")}</button>`;
    box.classList.remove("hidden");
    $("#fmt-best").onclick = () => startDownload({ format_id: null });
    return;
  }
  // Gom nhóm: video có cả audio, video-only (cần FFmpeg ghép), audio-only
  const rows = m.formats.filter(f => f.height || !f.has_video).slice(0, 40);
  box.innerHTML = `<h3>Định dạng khả dụng (${m.formats.length})</h3>
    <table class="fmt-table"><tr><th></th><th>Chất lượng</th><th>Tên file</th><th>Phần mở rộng</th><th>Kích thước ước tính</th><th>Ghi chú</th></tr>` +
    rows.map((f, i) => `<tr>
      <td><input type="radio" name="fmt" value="${i}" ${i === 0 ? "checked" : ""}></td>
      <td>${esc(f.quality_label || f.resolution || "audio")}${!f.has_audio ? " <span class='chip warn'>video-only</span>" : ""}${!f.has_video ? " <span class='chip'>audio-only</span>" : ""}</td>
      <td>${esc(f.format_id)}</td><td>${esc(f.ext)}</td><td>${fmtBytes(f.filesize)}</td><td class="muted">${esc(f.note || "")}</td></tr>`).join("") +
    `</table><div class="row"><button class="btn primary" id="fmt-go">${t("download")}</button>
     <label class="chk"><input type="checkbox" id="fmt-audio"> Chỉ lấy âm thanh (mp3/m4a)</label></div>`;
  box.classList.remove("hidden");
  $("#fmt-go").onclick = () => {
    const i = +box.querySelector("input[name=fmt]:checked").value;
    const f = rows[i];
    const audioOnly = $("#fmt-audio").checked;
    startDownload({ format_id: audioOnly ? null : f.format_id, audio_only: audioOnly, audio_format: audioOnly ? "mp3" : null });
  };
}

async function startDownload(extra) {
  if (!currentMeta) return;
  const opts = { url: currentMeta.url, skip_duplicate: true, ...extra };
  try {
    const task = await api("/tasks", { method: "POST", body: JSON.stringify(opts) });
    currentTaskId = task.id;
    subscribeTask(task.id);
    renderTaskCard(task);
    $("#dl-task").classList.remove("hidden");
    msg("#dl-detect", t("added"), "ok");
  } catch (e) { msg("#dl-detect", e.message, "err"); }
}

/* ------------------------- progress qua SSE ----------------------------- */
/* Backend phát: {event:"progress", task_id, percent, downloaded_bytes,...} và
   {event:"task_updated", task:{...}} / task_completed / task_failed. */
function subscribeTask(id) {
  if (evtSource) evtSource.close();
  currentTaskId = id;
  evtSource = new EventSource(`${API}/api/events/${id}`);
  evtSource.onmessage = (ev) => {
    const d = JSON.parse(ev.data);
    if (d.event === "progress") updateTaskUI(d);
    if (d.event === "task_updated" && d.task) applyTaskSnapshot(d.task);
    if (d.event === "task_completed") { applyTaskSnapshot({ state: "completed", file_path: d.file_path, progress: { percent: 100 } }); evtSource.close(); refreshQueueBadge(); }
    if (d.event === "task_failed") { applyTaskSnapshot({ state: "failed", error: d.error }); evtSource.close(); refreshQueueBadge(); }
  };
  evtSource.onerror = () => { /* tự reconnect; dot topbar báo mất backend */ };
}

function renderTaskCard(task) {
  const box = $("#dl-task");
  box.innerHTML = `<h3>Tác vụ đang chạy</h3><div class="task" id="live-task"></div>`;
  $("#live-task")._task = task;
  drawTaskInto($("#live-task"), task, true);
}
function updateTaskUI(d) {
  const p = d.progress ? d : { progress: d }; // event progress dẹt: percent... nằm gốc
  const box = $("#dl-task"); if (!box || box.classList.contains("hidden")) return;
  const bar = box.querySelector(".bar i"), pct = box.querySelector(".pct"), info = box.querySelector(".t-info");
  const pr = d.progress || d;
  if (bar) bar.style.width = (pr.percent || 0) + "%";
  if (pct) pct.textContent = (pr.percent || 0).toFixed(1) + "%";
  if (info) info.textContent = `${fmtBytes(pr.downloaded_bytes)} / ${fmtBytes(pr.total_bytes)} · ${pr.speed_bps ? fmtBytes(pr.speed_bps) + "/s" : ""} ${pr.eta_seconds ? "· còn ~" + Math.round(pr.eta_seconds) + "s" : ""}`;
}
/* Cập nhật thẻ tác vụ live theo snapshot task (state/error/file_path/progress). */
function applyTaskSnapshot(task) {
  const node = $("#live-task");
  if (!node) return;
  if (task.state || task.error || task.file_path || task.progress) {
    const merged = Object.assign({}, node._task || {}, task);
    node._task = merged;
    drawTaskInto(node, merged, true);
  } else if (task.id) {
    node._task = task; drawTaskInto(node, task, true);
  }
  refreshQueueBadge();
}

/* ================================ QUEUE ================================= */
const STATE_LABEL = { pending: "pending", queued: "queued", analyzing: "analyzing", downloading: "downloading", processing: "processing", paused: "paused", completed: "completed", failed: "failed", cancelled: "cancelled" };

function drawTaskInto(node, task, live) {
  if (task.id || task.state) node._task = Object.assign({}, node._task || {}, task);
  const pr = (node._task && node._task.progress) || task.progress || {};
  node.innerHTML = `
    <div class="t-head">
      <span class="t-title" title="${esc(task.title || task.url)}">${esc(task.title || task.url)}</span>
      <span class="state ${task.state}">${esc(task.state)}</span>
    </div>
    <div class="prog"><div class="bar"><i style="width:${pr.percent || 0}%"></i></div><span class="pct">${(pr.percent || 0).toFixed(0)}%</span></div>
    <div class="t-info muted">${pr.downloaded_bytes ? fmtBytes(pr.downloaded_bytes) + " / " + fmtBytes(pr.total_bytes) : esc((node._task && (node._task.url || (node._task.options && node._task.options.url))) || "")}</div>
    ${task.error ? `<div class="errbox">${esc(task.error.message || "")}<br><small>${esc(task.error.hint_vi || "")}</small></div>` : ""}
    ${task.state === "completed" && task.file_path ? `<div class="msgline ok">✔ ${esc(task.file_path)} · ${fmtBytes(task.file_size)}</div>` : ""}
    <div class="t-actions"></div>`;
  const acts = node.querySelector(".t-actions");
  const btn = (label, cls, fn) => { const b = el("button", "btn small " + cls, label); b.onclick = fn; acts.appendChild(b); };
  if (["downloading", "analyzing", "processing"].includes(task.state)) btn(t("pause"), "ghost", () => act(`/tasks/${task.id}/pause`));
  if (task.state === "paused") btn(t("resume"), "ghost", () => act(`/tasks/${task.id}/resume`));
  if (["downloading", "queued", "pending", "paused", "analyzing"].includes(task.state)) btn(t("cancel"), "danger", () => act(`/tasks/${task.id}/cancel`));
  if (task.state === "failed") btn(t("retry"), "ghost", () => act(`/tasks/${task.id}/retry`, "post"));
  if (["completed", "failed", "cancelled"].includes(task.state)) btn(t("remove"), "ghost", () => act(`/tasks/${task.id}`, "del"));
  if (task.state === "completed" && task.file_path) btn(t("reveal"), "ghost", () => act("/files/reveal", "post", { file_path: task.file_path }));
}

async function act(path, mode = "post", body) {
  const opts = { method: mode === "del" ? "DELETE" : mode.toUpperCase() };
  if (body) opts.body = JSON.stringify(body);
  try { await api(path, opts); refreshQueue(); } catch (e) { alert(e.message); }
}

async function refreshQueue() {
  try {
    const { tasks, stats } = await api("/tasks");
    $("#q-stats").innerHTML = Object.entries(stats).map(([k, v]) => `<span class="chip">${esc(k)}: <b>${v}</b></span>`).join("");
    const list = $("#q-list"); list.innerHTML = "";
    if (!tasks.length) list.innerHTML = '<p class="muted">Hàng đợi trống.</p>';
    for (const task of tasks.slice().reverse()) { const d = el("div", "task"); list.appendChild(d); drawTaskInto(d, task); }
    setBadge(stats.pending + stats.active);
  } catch (e) { $("#q-list").innerHTML = `<div class="errbox">${esc(e.message)}</div>`; }
}
$("#q-refresh").onclick = refreshQueue;

function setBadge(n) { const b = $("#badge-queue"); b.textContent = n > 0 ? n : ""; }
async function refreshQueueBadge() { try { const { stats } = await api("/tasks"); setBadge(stats.pending + stats.active); } catch {} }

/* =============================== HISTORY ================================ */
async function refreshHistory() {
  try {
    const { history } = await api("/history");
    const list = $("#h-list"); list.innerHTML = "";
    if (!history.length) { list.innerHTML = '<p class="muted">Chưa có mục nào. Lịch sử chỉ ghi khi file được lưu HOÀN CHỈNH.</p>'; return; }
    for (const h of history) {
      const d = el("div", "task");
      d.innerHTML = `<div class="t-head"><span class="t-title">${esc(h.title)}</span><span class="state ${h.state}">${esc(h.state)}</span></div>
        <div class="t-info muted">${esc(h.file_path)} · ${fmtBytes(h.file_size_on_disk ?? h.file_size)} · ${esc(h.completed_at)} ${h.file_exists ? "" : "· ⚠ file không còn trên đĩa"}</div>
        <div class="t-actions"></div>`;
      const acts = d.querySelector(".t-actions");
      const mk = (label, cls, fn) => { const b = el("button", "btn small " + cls, label); b.onclick = fn; acts.appendChild(b); };
      if (h.file_exists) mk(t("reveal"), "ghost", () => act("/files/reveal", "post", { file_path: h.file_path }));
      mk(t("delete_hist"), "danger", async () => {
        if (!confirm("Xóa MỤC LỊCH SỬ này? File gốc sẽ KHÔNG bị xóa.")) return;
        await act(`/history/${h.id}`, "del"); refreshHistory();
      });
      list.appendChild(d);
    }
  } catch (e) { $("#h-list").innerHTML = `<div class="errbox">${esc(e.message)}</div>`; }
}
$("#h-refresh").onclick = refreshHistory;

/* ================================ BATCH ================================= */
$("#batch-add").onclick = async () => {
  const urls = $("#batch-urls").value.split(/\n+/).map(s => s.trim()).filter(Boolean);
  if (!urls.length) return msg("#batch-msg", "Chưa có URL nào.", "info");
  const best = $("#batch-best").checked;
  const results = [];
  for (const u of urls) {
    try { await api("/tasks", { method: "POST", body: JSON.stringify({ url: u, skip_duplicate: true, ...(best ? {} : {}) }) }); results.push([u, "ok"]); }
    catch (e) { results.push([u, e.message]); }
  }
  $("#batch-urls").value = "";
  $("#batch-msg").innerHTML = results.map(([u, r]) => `<div class="msgline ${r === "ok" ? "ok" : "err"}">${esc(u)} → ${esc(r)}</div>`).join("");
  refreshQueueBadge();
};

/* ============================== SETTINGS ================================ */
async function refreshSettings() {
  try {
    const { download_dir } = await api("/settings/download-dir");
    $("#set-dir").value = download_dir;
    if (healthCache) $("#set-health").innerHTML =
      `<span class="chip ${healthCache.ffmpeg_available ? "ok" : "warn"}">FFmpeg: ${healthCache.ffmpeg_available ? "sẵn sàng" : "CHƯA cài (ghép audio/video & mp3 sẽ giới hạn)"}</span>
       <span class="chip">yt-dlp: ${esc(healthCache.yt_dlp_version || "?")}</span>
       <span class="chip">API v${esc(healthCache.version)}</span>`;
  } catch (e) { msg("#set-msg", e.message, "err"); }
}
$("#set-dir-save").onclick = async () => {
  try { const r = await api("/settings/download-dir", { method: "PUT", body: JSON.stringify({ path: $("#set-dir").value }) }); msg("#set-msg", "Đã lưu: " + r.download_dir, "ok"); }
  catch (e) { msg("#set-msg", e.message, "err"); }
};

/* ============================== PLATFORMS =============================== */
async function refreshPlatforms() {
  try {
    const { platforms } = await api("/platforms");
    $("#p-list").innerHTML = '<div class="plat">' + platforms.map(p => `
      <div class="card"><b>${esc(p.display_name)}</b> ${statusChip(p.status)}
      <p class="muted">${esc(p.description_vi || "")}</p>
      ${p.conditions_vi ? `<p class="muted"><b>Điều kiện:</b> ${esc(p.conditions_vi)}</p>` : ""}
      ${p.max_resolution ? `<span class="chip">tối đa ${p.max_resolution}p</span>` : ""}</div>`).join("") + "</div>";
  } catch (e) { $("#p-list").innerHTML = `<div class="errbox">${esc(e.message)}</div>`; }
}

/* ================================ HOME ================================== */
async function refreshHomeStats() {
  try {
    const { stats } = await api("/tasks");
    const { history } = await api("/history");
    $("#home-stats").innerHTML = `
      <div class="stat"><b>${stats.active + stats.pending}</b><span>${t("tasks_total")} hoạt động</span></div>
      <div class="stat"><b>${stats.completed}</b><span>${t("completed")}</span></div>
      <div class="stat"><b>${stats.failed}</b><span>${t("failed_c")}</span></div>
      <div class="stat"><b>${history.length}</b><span>Lịch sử</span></div>`;
  } catch { $("#home-stats").innerHTML = ""; }
}

/* =============================== ABOUT ================================== */
async function fillAbout() {
  if (healthCache) $("#about-ver").textContent = `version ${healthCache.version} · yt-dlp ${healthCache.yt_dlp_version || "?"} · FFmpeg ${healthCache.ffmpeg_available ? "OK" : "missing"}`;
}

/* ================================ INIT ================================== */
(async function init() {
  applyTheme();
  await ping();
  applyLang();
  await fillAbout();
  refreshQueueBadge();
})();
