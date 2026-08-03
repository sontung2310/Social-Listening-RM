import { MOCK_RESULTS, MOCK_HISTORY } from "./mock_data.js";

const CFG = window.RM_TOOL_CONFIG || {};
const BASE = (CFG.API_BASE || "").replace(/\/+$/, "");

function sleep(ms){ return new Promise(r=>setTimeout(r, ms)); }

async function req(path, { method="GET", body, headers={} } = {}) {
  const url = `${BASE}${path.startsWith("/") ? "" : "/"}${path}`;
  const init = { method, headers: { "Content-Type":"application/json", ...headers } };
  if (body !== undefined) init.body = JSON.stringify(body);
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return await r.json();
}

export async function apiSearch({ subject, days=7, limit=10, location="", industry="" }) {
  if (CFG.USE_MOCK) { await sleep(400); return Array.from(MOCK_RESULTS).slice(0, limit); }
  return req("/search", { method:"POST", body: { subject, day: days, limit, location, industry } });
}

export async function apiHistory({ page=1, page_size=20 } = {}) {
  if (CFG.USE_MOCK) { await sleep(200); return MOCK_HISTORY; }
  return req(`/history?page=${page}&page_size=${page_size}`);
}

export async function apiFilters() {
  if (CFG.USE_MOCK) { return { topics: ["AI","Value Care","Workforce"], industries: ["Healthcare"], locations: ["AU","US"] }; }
  return req("/filters");
}
