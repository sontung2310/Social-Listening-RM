export const MOCK_RESULTS = [
  {
    title: "AI in Healthcare: 2025 Outlook",
    url: "#",
    source_key: "news_rss",
    published_ts: 1737744000, // 2025-01-25
    text_html: "<p>Hospitals adopt LLMs for triage and coding.</p>",
    engagement: { score: 82, num_comments: 14, upvote_ratio: 0.92, total_awards: 1 }
  },
  {
    title: "HackerNews: LLMs reduce prior auth delays",
    url: "#",
    source_key: "hackernews_api",
    published_ts: 1738352400, // 2025-02-01
    text_html: "<p>Insurer pilots show 30% faster approvals.</p>",
    engagement: { score: 65, num_comments: 48, upvote_ratio: 0.86, total_awards: 0 }
  }
];

export const MOCK_HISTORY = {
  items: [
    { created_at: "2025-02-28T10:15:00Z", subject: "AI Healthcare", result_count: 2 },
    { created_at: "2025-02-26T13:05:00Z", subject: "Workforce Health", result_count: 7 },
    { created_at: "2025-02-25T09:40:00Z", subject: "Value-based care", result_count: 3 }
  ],
  total: 3, page: 1, page_size: 20
};
