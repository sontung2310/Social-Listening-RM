# Workers — AI queue consumer

Consumes **`social_listening_crawling_response`** (architecture `crawl.ai.queue`):
Data-Crawler-Task `raw_collected` events → NLP via `ai/` → cloud Mongo **`ai_posts`** / **`ai_comments`**.

## Backends

| `AI_QUEUE_BACKEND` | Behavior |
|--------------------|----------|
| `sim` (default if unset) | Loads `workers/sample_messages/input/*.json` |
| `sqs` | Long-polls `SQS_AI_QUEUE_URL` (WaitTimeSeconds from `SQS_WAIT_TIME_SECONDS`, max 20) |

On success the worker deletes the SQS message. On failure it leaves the message for AWS redrive / DLQ.

## Sample messages (sim only)

| Input file | Type | Source |
|------------|------|--------|
| `input/post_x.json` | post | X / Twitter (`x_playwright`) |
| `input/post_youtube.json` | post | YouTube |
| `input/post_news.json` | post | NewsAPI (`newsapi`) |
| `input/post_duckduckgo.json` | post | DuckDuckGo web (`duckduckgo_web`) |
| `input/post_rss.json` | post | BBC RSS (`bbc_rss`) |
| `input/comment_reddit.json` | comment | Reddit (`reddit_playwright`) |
| `input/comment_youtube.json` | comment | YouTube |

After `python -m workers --once` (sim), matching files appear under `output/`.

## Run

```bash
cd code/Backend
source ../../.venv/bin/activate   # or your venv

# credentials/backend.env: AI_QUEUE_BACKEND=sqs + AWS_* + SQS_AI_QUEUE_URL
python -m workers --once   # process available messages once
# or: python -m workers    # long-running loop
```

Requires `MONGODB_URI` / `MONGODB_DBNAME` in `credentials/backend.env` for cloud writes.

## Message shape

Same as Data-Crawler-Task `events.py` → SQS body:

- Envelope: `event_id`, `schema_version`, `event_type=raw_collected`, `content_type`, `source`, `external_id`, `history_id`, `payload`
- `payload`: adapter row from DCT `sources/` (`text`, `title`, `url`, …)
