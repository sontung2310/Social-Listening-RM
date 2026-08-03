const { API_BASE } = window.RM_TOOL_CONFIG;

async function run() {
  const subject = sessionStorage.getItem("rm:q");
  const days = Number(sessionStorage.getItem("rm:days") || 7);
  const limit = Number(sessionStorage.getItem("rm:limit") || 10);

  const target = document.getElementById("resultsRoot");
  target.textContent = "Loading...";

  try {
    const r = await fetch(`${API_BASE}/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject, day: days, limit })
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    const { items } = await r.json();

    // render very simply
    target.innerHTML = items.map(x => `
      <div class="card">
        <h3>${x.title || "(no title)"}</h3>
        <p>${x.summary || ""}</p>
      </div>
    `).join("") || "<p>No results.</p>";
  } catch (e) {
    target.innerHTML = `<p style="color:#c00">Request failed: ${e.message}</p>`;
  }
}

document.addEventListener("DOMContentLoaded", run);
