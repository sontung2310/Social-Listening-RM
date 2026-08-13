# Future work

Problems and follow-ups deferred from the Backend cleanup (crawl/Kafka removal + restructure). Treat [`SYSTEM_ARCHITECTURE.md`](SYSTEM_ARCHITECTURE.md) as the source of truth.

## Checklist

### 1. Crawl Management API (replaces stubbed `POST /api/search/`)

- [x] Implement crawl job acceptance on Pace-Unit (`POST /api/crawl/`).
- [x] Persist job metadata in `crawl_jobs`.
- [x] Publish commands to SQS `social_listening_data_crawling` (`crawl.command.queue`) for **Data-Crawler-Task**.
- [x] Expose job status endpoints the dashboard can poll (`GET /api/crawl/<job_id>/`).
- [ ] Remove or permanently retire the current `501` stub on `POST /api/search/`.

### 2. Frontend new-search integration

- [ ] Stop calling stubbed `POST /api/search/` for new searches (it returns **501** today).
- [ ] Wire the search / crawl UI to the new Crawl Management API and status endpoints.
- [ ] Keep reading existing history/results from Mongo where still valid.

### 3. AI worker pool (`workers/`)

- [x] **Simulated** consumer of `crawl.ai.queue` (`AI_QUEUE_BACKEND=sim` + `sample_messages/`) — see `code/Backend/workers/`
- [x] Wire real AWS SQS receive/delete (`AI_QUEUE_BACKEND=sqs` → `SQS_AI_QUEUE_URL`)
- [x] Run NLP via `ai/` (sentiment, topics, summarization) per message
- [x] Write enriched results to cloud Mongo `ai_posts` / `ai_comments`
- [x] On failure, leave message for AWS DLQ redrive; delete only after successful cloud save

### 4. Credential / config cleanup

- [x] Add AWS / SQS env vars for command queue, AI queue, and DLQ.
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
