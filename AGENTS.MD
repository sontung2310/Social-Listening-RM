# Robotic Marketer AI Listening Tool — Agent Guide

This document guides AI agents working in the `code/` directory of the Robotic Marketer AI Listening Tool (PACE Unit).

---

## Project overview

The Robotic Marketer AI Listening Tool is a **social listening** platform that scores crawled content for relevance using ML, summarizes results for review, and presents them through a web-based search interface.

### System architecture (required reading)

**Before any implementation work**, read and follow [`SYSTEM_ARCHITECTURE.md`](./SYSTEM_ARCHITECTURE.md).

That document is the **source of truth** for the overall system design (AWS EC2 / Local Crawling Environment / AWS EC2) and the end-to-end sequence. Implementation must match it strictly — do not introduce alternate flows, queues, data stores, or environment splits that conflict with it. If the design must change, ask me for confirmation first; only after I explicitly accept may you update `SYSTEM_ARCHITECTURE.md`.

Crawl execution lives in the sibling repo `Data-Crawler-Task`; this repo (`Pace-Unit`) owns the dashboard, typed crawl-management API, response workers, AI analysis, and related cloud services. Deferred work is listed in [`FUTURE_WORK.md`](./FUTURE_WORK.md).

### Core capabilities

- **Crawl (external)** — Source crawlers live in **Data-Crawler-Task**, not in this repo. Do not re-add `api/sources/` here.
- **Relevance scoring and ranking** — ML ranking pipeline in `Backend/ai/ranking_algorithm/` combines BM25, SBERT, TF-IDF, engagement scores, and word-count penalties into weighted relevance scores.
- **Summarization** — Extractive 4-line summaries via TF-IDF sentence scoring in `Backend/ai/Text_summarisation/` (no LLM for search-result summaries).
- **Groq LLM features** — Groq API (`Backend/ai/collection_card/gpt.py`) powers company-aware collection cards: trending topics, news feed analysis, ideas, competitor detection, opportunities, and engaged links.
- **Web interface** — Django frontend at `Frontend/` lets users search, filter, and view ranked results. Communicates with the Backend via `Frontend/ai_listening_tool/static/ai_listening_tool/js/config.js`.

### Crawl flow

The current production-shaped flow is:

```text
Dashboard/API or schedule trigger
  → SQS crawl.command.queue
  → Data-Crawler-Task
  → SQS crawl.ai.queue
  → Pace-Unit response worker
  → Article MongoDB or separate Dashboard MongoDB
```

There are two typed pipelines:

- `content_crawl` commands produce one or more `article_collected` events (`post` or `comment`). The response worker enriches them and stores them in `ai_posts` / `ai_comments` in the article database.
- `influencer_discovery` commands are owned end-to-end by Data-Crawler-Task. Pace publishes the complete request and proxies status; no influencer response event is produced. Run the explicit DCT dashboard export after a successful task.

`POST /api/search/` is a legacy 501 endpoint. New crawl requests must use `POST /api/crawl/`. History / results / cards endpoints that read existing Mongo data remain available.

---

## Environment

Use **one shared virtual environment at the repo root** (`Pace-Unit/.venv`). Install dependencies from the Backend and Frontend `requirements.txt` files (plus `Backend/ai/requirements.txt` if installing AI extras separately).

### Prerequisites

- Python 3.11+ (repo uses Python 3.11)
- MongoDB Atlas cluster (or local MongoDB)
- API keys for dashboard features (SerpAPI, NewsAPI, Groq) — crawl keys belong in Data-Crawler-Task

### Setup

```bash
# From repo root: Pace-Unit/
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows
# .venv\Scripts\activate

pip install -r code/Backend/ai/requirements.txt
pip install -r code/Backend/requirements.txt
pip install -r code/Frontend/requirements.txt
```

**Install order:** AI first (lighter ML stack), then Backend (Flask + shared ML deps), then Frontend (Django extras).

### Pre-run checklist

1. Copy `code/Backend/credentials/backend_example.env` → `code/Backend/credentials/backend.env` and fill in API keys, AWS/SQS settings, article MongoDB, and dashboard MongoDB settings.
2. Configure `code/Backend/ai/AI.env` with `MONGO_URI` and `GROQ_API_KEY` for legacy/card AI modules.
3. Configure the sibling `Data-Crawler-Task/.env` with the same command/response SQS queues and its crawl credentials.
4. Set `API_BASE` in `code/Frontend/ai_listening_tool/static/ai_listening_tool/js/config.js` to `http://127.0.0.1:8000/api`.

---

## Run commands

Start the services below in separate terminals. The crawler and backend both use their repository virtual environments.

| Service | Working directory | Command | URL / purpose |
|---------|-------------------|---------|---------------|
| Data crawler | `Data-Crawler-Task` | `uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1` | `http://127.0.0.1:8001/health`; starts command consumer |
| Backend API | `code/Backend` | `python app.py 8000` | `http://127.0.0.1:8000/api/health/` |
| Response worker | `code/Backend` | `AI_QUEUE_BACKEND=sqs python -m workers` | consumes article response events only |
| Frontend (optional UI) | `code/Frontend` | `python manage.py runserver 8002` | `http://127.0.0.1:8002/tool/` |

```bash
# Each terminal starts from the Pace-Unit repository root.

# Terminal 1 — Data-Crawler-Task (starts its command SQS consumer)
cd ../Data-Crawler-Task
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1

# Terminal 2 — Pace-Unit Backend API
source .venv/bin/activate
cd code/Backend
python app.py 8000

# Terminal 3 — Pace-Unit response worker
source .venv/bin/activate
cd code/Backend
AI_QUEUE_BACKEND=sqs python -m workers

# Terminal 4 — optional Frontend
source .venv/bin/activate
cd code/Frontend
python manage.py runserver 8002
```

For local fixture processing only, run `python -m workers --once` with the default `AI_QUEUE_BACKEND=sim`. Use `AI_QUEUE_BACKEND=sqs` for the complete pipeline. Kafka was removed from this repo.

### Trigger a complete pipeline run

Once the crawler, backend API, and response worker are running, either submit a persisted job through `POST /api/crawl/` or use the direct SQS trigger scripts. The scripts print their generated `job_id` and command; they do **not** create a `crawl_jobs` record.

```bash
# From Pace-Unit/code, with Pace-Unit/.venv activated
python schedule_run/trigger_article_pipeline.py \
  --query "Digital Marketing Trends" --source all --time-delta week --limit 20

python schedule_run/trigger_influencer_pipeline.py \
  --field "Marketing" --company-id company-123 --company-name "Marketing Eye" \
  --company-domain marketingeye.com.au \
  --company-summary "A marketing agency helping brands grow." \
  --related-terms "SEO,content marketing" --limit 20
```

All influencer identity and topic fields are required. The same job ID is used as the DCT task ID; poll DCT for status and use its explicit export command for dashboard writes.

### Frontend routes

| Path | Page |
|------|------|
| `/tool/` | Main search page |
| `/tool/results/` | Latest results |
| `/tool/history/` | Search history |
| `/tool/simple/` | Simple text-only results |
| `/tool/debug/` | Debug view |

---

## Project structure

Directory tree for `code/` with one-line purpose per major folder.

```
code/
├── FUTURE_WORK.md                             # Remaining integration and operations work
├── SYSTEM_ARCHITECTURE.md                     # Source-of-truth architecture
├── AGENTS.MD                                  # This file
├── Backend/
│   ├── app.py                                 # Flask app entry point
│   ├── config.py                              # Env loading, API keys, MongoDB, sys.path
│   ├── requirements.txt                       # Backend Python dependencies
│   ├── README.md                              # Backend setup and API reference
│   ├── api/                                   # HTTP layer
│   │   ├── __init__.py
│   │   ├── analytics.py                       # Trends, tags, source breakdown analytics
│   │   ├── crawl.py                           # Typed crawl-job acceptance/status API
│   │   ├── cleanup_raw_insights.py            # Raw data cleanup utilities
│   │   └── views.py                           # Flask route handlers
│   ├── db/                                    # MongoDB helpers
│   │   ├── __init__.py
│   │   ├── persist.py                         # Article/history Mongo helpers
│   │   ├── ai_store.py                        # Upserts for ai_posts / ai_comments
│   │   └── ...                                # Article/database helpers; influencer export is DCT-owned
│   ├── ai/                                    # AI/ML modules — ranking, summarization, collection cards
│   │   ├── __init__.py
│   │   ├── AI.env                             # AI credentials (MONGO_URI, GROQ_API_KEY)
│   │   ├── collection_card/                   # Company-aware Groq-powered AI cards
│   │   ├── ranking_algorithm/                 # Search-result ranking, sentiment, pipeline
│   │   ├── sentiment_analysis/                # VADER-based sentiment scoring
│   │   ├── Text_summarisation/                # Extractive article summarization (TF-IDF)
│   │   ├── Topic_detection/                   # Topic extraction from article text
│   │   ├── README_CREDENTIALS.md
│   │   └── requirements.txt
│   ├── publishers/                            # Typed crawl-command SQS publisher
│   ├── workers/                               # SQS response consumer: article events only
│   │   ├── README.md
│   │   ├── queue.py                           # SimulatedQueue (receive/delete)
│   │   ├── events.py                          # article_collected response validation
│   │   ├── process.py                         # Article NLP + upsert
│   │   ├── consumer.py                        # Article response-event worker only
│   │   ├── consumer.py                        # Event routing / loop / --once
│   │   ├── sample_io.py                       # Write sample_messages/output
│   │   └── sample_messages/
│   │       ├── input/                         # DCT-shaped queue samples
│   │       └── output/                        # AI-enriched results for inspection
│   ├── credentials/
│   │   ├── backend_example.env                # Template for backend.env
│   │   └── backend.env                        # Backend API keys and MongoDB URI (not committed)
│   └── tests/
│       └── __init__.py
├── schedule_run/                              # Direct typed SQS trigger scripts
│   ├── trigger_article_pipeline.py
│   └── trigger_influencer_pipeline.py
└── Frontend/                                  # Django web UI
    ├── ai_listening_tool/                     # Main Django app — templates, static assets, views
    ├── manage.py
    ├── Readme.md
    └── requirements.txt
```

**Note:** Static JS/CSS exists in both `ai_listening_tool/static/` and `ai_listening_tool/listening_tool/static/`. Edit the **top-level** `ai_listening_tool/static/` copies (they include `img/` assets) unless working specifically on the nested app.

---

## Code convention

### Type hints

Always provide type hints for every function that is **not** a view handler.

- **Exempt:** Flask `@api_bp.route` functions in `Backend/api/views.py` and Django page functions in `Frontend/ai_listening_tool/views.py`.
- **Required everywhere else:** ranking scorers, AI modules, persistence helpers, tests.
- Follow patterns in `Backend/ai/ranking_algorithm/main.py`.

### Simplicity over abstraction

Avoid using helper functions and complex structures when something can easily be solved with a single function. Do not split one-off logic into private `_helper` chains unless there is genuine reuse.

### Additional conventions

- **Environment loading:** Use `python-dotenv` + `Path(__file__)`. Backend reads `credentials/backend.env`; AI modules read `ai/AI.env`.
- **AI imports:** Use `from ai.<module>...` style. `config.py` puts the Backend root on `sys.path`.
- **Mongo helpers:** Import via `from db.persist import ...`.
- **Crawl sources:** Live in **Data-Crawler-Task** only. Do not add fetchers under Pace-Unit Backend.
- **Timestamps:** Source/crawl fields like `published_ts` and `crawled_at` use **Unix epoch seconds** (`int`), not ISO 8601. Keep new time fields in the same format unless converting at an API/display boundary.
- **Credentials:** Never commit `.env` files. Use `backend_example.env` as a template only (see `code/.gitignore`).
- **Queues:** Use SQS per architecture — do not reintroduce Kafka.

---

## Credentials

| File | Key variables | Used by |
|------|---------------|---------|
| `Backend/credentials/backend.env` | AWS/SQS vars; `ARTICLE_MONGODB_URI`, `ARTICLE_MONGODB_DBNAME`; `DASHBOARD_DATABASE_HOST`, `DASHBOARD_DATABASE_NAME`, `DASHBOARD_DATABASE_USERNAME`, `DASHBOARD_DATABASE_PASSWORD`; dashboard API keys | API, command publisher, response worker |
| `Backend/ai/AI.env` | `MONGO_URI`, `GROQ_API_KEY` | All AI modules |

### Setup

```bash
# Backend credentials
cp code/Backend/credentials/backend_example.env code/Backend/credentials/backend.env
# Edit backend.env with API keys, SQS settings, article MongoDB, and dashboard MongoDB settings

# AI credentials — edit code/Backend/ai/AI.env directly
# Set MONGO_URI and GROQ_API_KEY for legacy/card AI modules
```

**Database split:** `ARTICLE_MONGODB_URI` / `ARTICLE_MONGODB_DBNAME` (or legacy `MONGODB_*` fallbacks) are for article AI data. The four `DASHBOARD_DATABASE_*` variables connect to the separate Robotic Marketer dashboard MongoDB. Do not merge these connections or reuse the dashboard credentials for article persistence.

---

## Key API endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health/` | GET | Health check |
| `/api/crawl/` | POST | Accept a typed `content_crawl` or `influencer_discovery` job and publish it to SQS |
| `/api/crawl/<job_id>/` | GET | Return persisted crawl-job status |
| `/api/search/` | POST | **501 stub** — crawl ingest moved to Data-Crawler-Task; see `FUTURE_WORK.md` |
| `/api/search/status/` | GET | Poll AI processing progress by `history_id` |
| `/api/results/` | GET | Paginated ranked + summarized results |
| `/api/history/` | GET | List past searches |
| `/api/trends/` | GET | Timeseries trends for a `history_id` |
| `/api/topics/top/` | GET | Global trending topics |
| `/api/company/` | GET | Company profile lookup |
| `/api/cards/trending/` | GET | Company-aware trending topics (Groq) |
| `/api/cards/newsfeed/` | GET | AI-ranked company news feed (Groq) |
| `/api/ai/ideas/` | GET | AI idea suggestions (Groq) |
| `/api/ai/competitors/` | POST | Competitor detection from text (Groq) |
| `/api/ai/backlinks/` | GET | Engaged links / backlinks for a company |
| `/api/ai/opportunities/` | GET | Business opportunities (Groq) |
| `/api/company/upsert/` | POST | Create or update company profile |
| `/api/companies/` | GET | List companies |
| `/api/debug/mongo/` | GET | MongoDB collection names and document counts |

### Crawl request flow

```
POST /api/crawl/ → create crawl_jobs entry → SQS crawl.command.queue
GET /api/crawl/<job_id>/ → poll current job state
```

---

## Testing commands

```bash
# Backend health check (from code/Backend, venv activated)
cd code/Backend
python app.py 8000

curl -s http://127.0.0.1:8000/api/health/

# Submit an article crawl through the API
curl -s -X POST "http://127.0.0.1:8000/api/crawl/" \
  -H "Content-Type: application/json" \
  -d '{"task_type":"content_crawl","input":{"query":"Artificial Intelligence","source":"all","time_delta":"week","limit":20}}'

# Frontend page checks
curl -s http://127.0.0.1:8001/tool/
curl -s http://127.0.0.1:8001/tool/history/
curl -s http://127.0.0.1:8001/tool/results/
```

---

## Common pitfalls

- **Run all three backend services for a real crawl.** Data-Crawler-Task consumes commands, the Backend API submits/persists jobs, and the Pace response worker consumes results.
- **`POST /api/search/` returns 501.** It is legacy; create new jobs with `POST /api/crawl/` or the schedule triggers.
- **Separate Mongo targets.** Article AI data and dashboard influencer lists use different connections. Verify both the article and `DASHBOARD_DATABASE_*` settings before processing real SQS events.
- **Direct schedule triggers do not persist jobs.** Use `POST /api/crawl/` when dashboard polling of `crawl_jobs` is required.
- **Slow first AI run.** SBERT and spaCy models download on first use. Expect a long cold start.
- **Summarization vs Groq.** Search-result summaries are extractive (TF-IDF, no LLM). Groq is used only for `collection_card` features (ideas, competitors, news feed, etc.).
- **Do not commit credentials.** Use `backend_example.env` as a template. Real keys belong in `backend.env` and `AI.env`, which are gitignored.
- **Duplicate static files.** When editing Frontend JS/CSS, use the top-level `ai_listening_tool/static/` directory, not the nested `listening_tool/static/` copy.
- **Do not reintroduce Kafka or in-repo crawlers.** Use Data-Crawler-Task + SQS per architecture.
