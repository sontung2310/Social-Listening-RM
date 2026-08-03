# Future work

Problems and follow-ups deferred from the Backend cleanup (crawl/Kafka removal + restructure). Treat [`SYSTEM_ARCHITECTURE.md`](SYSTEM_ARCHITECTURE.md) as the source of truth.

## Checklist

### 1. Crawl Management API (replaces stubbed `POST /api/search/`)

- [ ] Implement crawl job acceptance on Pace-Unit (e.g. `POST /crawl` or a successor to `/api/search/`).
- [ ] Persist job metadata in `crawl_jobs`.
- [ ] Publish commands to SQS `crawl.command.queue` for the local worker in **Data-Crawler-Task**.
- [ ] Expose job status endpoints the dashboard can poll.
- [ ] Remove or permanently retire the current `501` stub on `POST /api/search/`.

### 2. Frontend new-search integration

- [ ] Stop calling stubbed `POST /api/search/` for new searches (it returns **501** today).
- [ ] Wire the search / crawl UI to the new Crawl Management API and status endpoints.
- [ ] Keep reading existing history/results from Mongo where still valid.

### 3. AI worker pool (`workers/`)

- [ ] Consume SQS `crawl.ai.queue` events published by Data-Crawler-Task after local raw upsert.
- [ ] Run NLP / ranking via `ai/` (sentiment, topics, summarization, ranking).
- [ ] Write enriched results to cloud Mongo (`ai_posts` / `ai_comments` or current `ai_results` model).
- [ ] On failure, route to SQS DLQ; delete the AI queue message only after successful cloud save.

### 4. Credential / config cleanup

- [ ] Add AWS / SQS env vars for command queue, AI queue, and DLQ.
- [ ] Confirm crawl-only API keys (Guardian, YouTube, Reddit, Playwright, etc.) live only in **Data-Crawler-Task**.
- [ ] Keep Pace-Unit keys that the dashboard still needs (e.g. `SERPAPI_KEY`, `NEWSAPI_KEY`, Mongo, Groq).

### 5. Optional cleanup of legacy search/history model

- [ ] Decide whether `history` + `/api/search/status/` remain or are replaced by `crawl_jobs`.
- [ ] Remove unused history helpers / docs once the jobs model is live.
- [ ] Update `AGENTS.MD` endpoint table after the new API ships.

## Notes

- **Data-Crawler-Task** owns source crawlers, local Mongo raw upsert, and AI event publish.
- **Pace-Unit** owns the web dashboard, crawl command API (pending), AI workers (pending), and analytics read path.
- Kafka was removed from this repo; do not reintroduce it — use SQS per architecture.
