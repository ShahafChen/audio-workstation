async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: options.body ? { "Content-Type": "application/json" } : {},
    body: options.body && JSON.stringify(options.body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || res.statusText));
  return data;
}
const enc = encodeURIComponent;
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
function fmtBytes(n) {
  if (n == null) return "–";
  const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}
function fmtTime(s) {
  s = Math.max(0, Math.floor(s || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
function header(active) {
  document.body.insertAdjacentHTML("afterbegin", `<header><b>🎚 Audio Workstation</b>
    <a href="/" class="${active === "library" ? "on" : ""}">Library</a>
    <a href="/monitor" class="${active === "monitor" ? "on" : ""}">Monitor</a></header>`);
}
function jobBadge(job) {
  if (!job || job.status === "done") return "";
  if (job.status === "error") return `<span class="badge error" title="${esc(job.message)}">split failed</span>`;
  if (job.status === "queued") return `<span class="badge">queued</span>`;
  return `<span class="badge">splitting ${job.progress}%</span>`;
}
