// path: social-listening-tool/ai_listening_tool/static/ai_listening_tool/js/api.js
// Global config + helpers. No exports.
(function () {
  // Defaults if not defined elsewhere
  const cfg = (window.RM_TOOL_CONFIG = window.RM_TOOL_CONFIG || {
    API_BASE: "http://127.0.0.1:8000/api",
    timeoutMs: 20000,
  });

  function withTimeout(promise, ms) {
    return Promise.race([
      promise,
      new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), ms)),
    ]);
  }

  async function handle(res, method, path) {
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${method} ${path} ${res.status} ${text}`.trim());
    }
    const ct = res.headers.get("content-type") || "";
    return ct.includes("application/json") ? res.json() : res.text();
  }

  // Attach to window for use anywhere
  window.apiGet = async function apiGet(path, qs = {}) {
    const base = String(cfg.API_BASE || "").replace(/\/$/, "");
    const url = new URL(`${base}${path}`);
    Object.entries(qs).forEach(([k, v]) => v != null && url.searchParams.set(k, v));
    const res = await withTimeout(fetch(url.toString(), { credentials: "omit" }), cfg.timeoutMs);
    return handle(res, "GET", path);
  };

  window.apiPost = async function apiPost(path, body = {}) {
    const base = String(cfg.API_BASE || "").replace(/\/$/, "");
    const res = await withTimeout(
      fetch(`${base}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "omit",
        body: JSON.stringify(body),
      }),
      cfg.timeoutMs
    );
    return handle(res, "POST", path);
  };
})();
