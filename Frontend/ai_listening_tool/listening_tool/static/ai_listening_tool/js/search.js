// static/ai_listening_tool/js/search.js
document.addEventListener('DOMContentLoaded', () => {
  const form  = document.getElementById('searchForm');
  const q     = document.getElementById('q');
  const err   = document.getElementById('err');

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    err.textContent = '';
    if (!q.value.trim()) {
      err.textContent = 'Enter a subject';
      return;
    }
    const resultsUrl = form.dataset.resultsUrl; // from data-results-url
    // pass values via query string
    const url = new URL(resultsUrl, window.location.origin);
    url.searchParams.set('q', q.value.trim());
    url.searchParams.set('days', days.value || '7');
    url.searchParams.set('limit', limit.value || '10');
    window.location.assign(url.toString());
  });
});
