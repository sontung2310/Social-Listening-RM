import { api } from "./api.js";
function row(i){
  const when = i.ts ? new Date(i.ts).toLocaleString() : "";
  return `<tr><td>${i.subject || "Unknown"}</td><td>${i.count ?? 0}</td><td class="ta-right">${when}</td></tr>`;
}
document.addEventListener("DOMContentLoaded", async () => {
  const tbody = document.getElementById("rm-history-body");
  tbody.innerHTML = `<tr><td colspan="3">Loading…</td></tr>`;
  try{
    const { items=[] } = await api.history();
    tbody.innerHTML = items.length ? items.map(row).join("") : `<tr><td colspan="3">No history</td></tr>`;
  }catch(e){
    tbody.innerHTML = `<tr><td colspan="3">Error: ${e.message}</td></tr>`;
  }
});
