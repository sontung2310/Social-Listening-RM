"use strict";

document.addEventListener("DOMContentLoaded", () => {
  console.log("Results page JavaScript loaded");

  // Source of truth for API base
  const host = document.getElementById("rmtool") || document.body;
  const apiBase =
    (host.dataset.apiBase && host.dataset.apiBase.replace(/\/$/, "")) ||
    (window.RM_TOOL_CONFIG?.API_BASE && window.RM_TOOL_CONFIG.API_BASE.replace(/\/$/, "")) ||
    "http://127.0.0.1:8000/api";

  console.log("API Base URL:", apiBase);

  // Regions from results.html
  const loadingEl = document.querySelector('[data-region="loading"]');
  const errEl = document.querySelector('[data-region="error"]');
  const listEl = document.querySelector('[data-region="list"]');
  const pagerEl = document.querySelector('[data-region="pager"]');
  const titleEl = document.getElementById("resultsTitle");

  console.log("Found elements:", { loadingEl, errEl, listEl, pagerEl, titleEl });

  // Params
  const qs = new URLSearchParams(location.search);
  const subject = (qs.get("subject") || sessionStorage.getItem("rm_subject") || "").trim();
  const timeRangeSel = document.getElementById("timeRange");
  const prioritySel = document.getElementById("priority");

  // Populate header search input
  const headerSearchInput = document.getElementById("headerSearchInput");
  if (headerSearchInput && subject) {
    headerSearchInput.value = subject;
  }
  const defaultDays = Number(sessionStorage.getItem("rm_days")) || 7;
  if (timeRangeSel) timeRangeSel.value = String(defaultDays);

  console.log("Search subject:", subject);

  const defaultPriority = sessionStorage.getItem("rm_priority") || "all";
  if (prioritySel) prioritySel.value = defaultPriority;

  // Initial render
  if (titleEl) titleEl.textContent = `Results for "${subject}"`;
  fetchAndRenderResults(subject, defaultDays, defaultPriority, 1);

  // Event Listeners for filters
  timeRangeSel?.addEventListener("change", () => {
    const newDays = timeRangeSel.value;
    sessionStorage.setItem("rm_days", newDays);
    fetchAndRenderResults(subject, Number(newDays), prioritySel?.value || "all", 1);
  });

  prioritySel?.addEventListener("change", () => {
    const newPriority = prioritySel.value;
    sessionStorage.setItem("rm_priority", newPriority);
    fetchAndRenderResults(subject, Number(timeRangeSel?.value || 7), newPriority, 1);
  });

  // Function to fetch data and render results
  async function fetchAndRenderResults(currentSubject, days, priority, page) {
    console.log(`Fetching results for "${currentSubject}" (Days: ${days}, Priority: ${priority}, Page: ${page})`);

    if (loadingEl) loadingEl.style.display = "block";
    if (errEl) errEl.style.display = "none";
    if (listEl) listEl.innerHTML = "";
    if (pagerEl) pagerEl.innerHTML = "";

    try {
      const response = await fetch(`${apiBase}/search/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subject: currentSubject,
          days: days,
          limit: 50, // Fetch more to handle pagination client-side
          priority: priority,
        }),
      });

      if (!response.ok) {
        throw new Error(`API returned status ${response.status}`);
      }

      const data = await response.json();
      console.log("API Data received:", data);

      if (!Array.isArray(data)) {
        throw new Error("API response is not an array.");
      }

      if (data.length === 0) {
        if (listEl) listEl.innerHTML = `<div class="rm-empty">No results found for "${currentSubject}"</div>`;
        return;
      }

      // Client-side pagination logic
      const itemsPerPage = 10;
      const totalPages = Math.ceil(data.length / itemsPerPage);
      const startIndex = (page - 1) * itemsPerPage;
      const endIndex = startIndex + itemsPerPage;
      const paginatedData = data.slice(startIndex, endIndex);

      if (listEl) {
        listEl.innerHTML = paginatedData.map(card).join("");
      }

      // Render pager
      if (pagerEl) {
        pagerEl.innerHTML = generatePager(totalPages, page);
        pagerEl.querySelectorAll("button").forEach((button) => {
          button.addEventListener("click", () => {
            const newPage = parseInt(button.dataset.page);
            fetchAndRenderResults(currentSubject, days, priority, newPage);
          });
        });
      }
    } catch (error) {
      console.error("Error fetching or rendering results:", error);
      if (errEl) {
        errEl.style.display = "block";
        errEl.innerHTML = `Failed to load results: ${error.message}`;
      }
    } finally {
      if (loadingEl) loadingEl.style.display = "none";
    }
  }

  function relToPct(v) {
    return Math.round((v > 1 ? v : v * 100) || 0);
  }

  function generatePager(totalPages, currentPage) {
    let pagerHtml = "";
    for (let i = 1; i <= totalPages; i++) {
      pagerHtml += `<button data-page="${i}" class="${i === currentPage ? "is-current" : ""}">${i}</button>`;
    }
    return pagerHtml;
  }

  function meter(v) {
    return `<div class="rm-meter"><span style="width:${relToPct(v)}%"></span></div>`;
  }

  function card(p) {
    console.log("Creating card for:", p);

    // Backend only returns: ai_title, ai_summary, relevance_score
    const title = p.ai_title || p.title || "Untitled";
    const summary = p.ai_summary || p.summary || p.text || "No description available.";
    const source = p.source || "Unknown Source";
    const score = Math.round((p.relevance_score || 0) * 100);
    const url = p.url || "";
    const tags = Array.isArray(p.tags) ? p.tags.slice(0, 3) : []; // Limit to 3 tags

    // Format engagement
    let engagement = "0";
    if (p.engagement && typeof p.engagement === 'object') {
      engagement = p.engagement.score || p.engagement.num_comments || "0";
    } else if (p.engagement) {
      engagement = p.engagement;
    }

    // Format date
    let dateStr = "";
    if (p.published_ts) {
      try {
        const date = new Date(p.published_ts * 1000); // Convert Unix timestamp
        dateStr = date.toLocaleDateString();
      } catch (e) {
        console.log("Date parsing error:", e);
      }
    }

    const cardHTML = `
      <article class="rm-card">
        <header class="rm-card-h">
          <h4>${url ? `<a href="${url}" target="_blank" rel="noopener" style="color: inherit; text-decoration: none;">${title}</a>` : title}</h4>
          <div class="rm-meta">
            <div><span class="rm-badge">TRENDING</span></div>
            <div>Score: ${score}%</div>
            <div>Engagement: ${engagement}</div>
          </div>
        </header>
        <p class="rm-desc">${summary}</p>
        <footer class="rm-card-f">
          ${dateStr ? `<span class="rm-chip">📅 ${dateStr}</span>` : ""}
          <span class="rm-chip">📰 ${source}</span>
          ${tags.map(t => `<span class="rm-chip">#${t}</span>`).join("")}
          ${url ? `<a class="rm-link" href="${url}" target="_blank" rel="noopener">🔗 View Details</a>` : ""}
        </footer>
      </article>
    `;

    console.log("Generated card HTML:", cardHTML);
    return cardHTML;
  }
});