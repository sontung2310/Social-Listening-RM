// path: social-listening-tool/ai_listening_tool/static/ai_listening_tool/js/history.js
"use strict";

/**
 * Convert text to title case (capitalize first, last, and major words)
 */
function toTitleCase(str) {
  if (!str) return str;
  
  const minorWords = ['a', 'an', 'the', 'and', 'but', 'or', 'for', 'nor', 'on', 'at', 'to', 'from', 'by', 'in', 'of', 'with'];
  
  return str.toLowerCase().split(' ').map((word, index, array) => {
    // Always capitalize first and last word
    if (index === 0 || index === array.length - 1) {
      return word.charAt(0).toUpperCase() + word.slice(1);
    }
    // Capitalize if not a minor word
    if (!minorWords.includes(word)) {
      return word.charAt(0).toUpperCase() + word.slice(1);
    }
    return word;
  }).join(' ');
}

// Render one table row
function row(i) {
  const when = i.ts ? new Date(i.ts).toLocaleString() : "";
  const subject = toTitleCase(i.subject || "Unknown");
  return `<tr><td>${subject}</td><td>${i.count ?? 0}</td><td class="ta-right">${when}</td></tr>`;
}

document.addEventListener("DOMContentLoaded", async () => {
  const tbody = document.getElementById("rm-history-body");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="3">Loading…</td></tr>`;
  try {
    // Uses global helper from api.js
    const data = await window.apiGet("/history/");
    const items = Array.isArray(data?.items) ? data.items : [];
    tbody.innerHTML = items.length ? items.map(row).join("") : `<tr><td colspan="3">No history</td></tr>`;
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="3">Error: ${e.message}</td></tr>`;
  }
});
