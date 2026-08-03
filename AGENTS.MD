# Robotic Marketer AI Listening Tool — Agent Guide

This document guides AI agents working in the `code/` directory of the Robotic Marketer AI Listening Tool (PACE Unit).

---

## Project overview

The Robotic Marketer AI Listening Tool is a **social listening** platform that scores crawled content for relevance using ML, summarizes results for review, and presents them through a web-based search interface.

### System architecture (required reading)

**Before any implementation work**, read and follow [`SYSTEM_ARCHITECTURE.md`](./SYSTEM_ARCHITECTURE.md).

That document is the **source of truth** for the overall system design (AWS EC2 / Local Crawling Environment / AWS EC2) and the end-to-end sequence. Implementation must match it strictly — do not introduce alternate flows, queues, data stores, or environment splits that conflict with it. If the design must change, ask me for confirmation first; only after I explicitly accept may you update `SYSTEM_ARCHITECTURE.md`.

Crawl execution lives in the sibling repo `Data-Crawler-Task`; this repo (`Pace-Unit`) deploys to a single AWS EC2 and owns the dashboard, crawl management API (pending), AI analysis, and related cloud services. Deferred work is listed in [`FUTURE_WORK.md`](./FUTURE_WORK.md).

### Core capabilities

- **Crawl (external)** — Source crawlers live in **Data-Crawler-Task**, not in this repo. Do not re-add `api/sources/` here.
- **Relevance scoring and ranking** — ML ranking pipeline in `Backend/ai/ranking_algorithm/` combines BM25, SBERT, TF-IDF, engagement scores, and word-count penalties into weighted relevance scores.
- **Summarization** — Extractive 4-line summaries via TF-IDF sentence scoring in `Backend/ai/Text_summarisation/` (no LLM for search-result summaries).
- **Groq LLM features** — Groq API (`Backend/ai/collection_card/gpt.py`) powers company-aware collection cards: trending topics, news feed analysis, ideas, competitor detection, opportunities, and engaged links.
- **Web interface** — Django frontend at `Frontend/` lets users search, filter, and view ranked results. Communicates with the Backend via `Frontend/ai_listening_tool/static/ai_listening_tool/js/config.js`.

### Search / crawl flow (current vs target)

**Current:** `POST /api/search/` returns **501** (in-process crawl and Kafka were removed). See [`FUTURE_WORK.md`](./FUTURE_WORK.md).

**Target (architecture):** Dashboard → Crawl Management API → SQS `crawl.command.queue` → Data-Crawler-Task → local Mongo → SQS `crawl.ai.queue` → Pace-Unit AI workers → cloud Mongo → analytics UI.

History / results / cards endpoints that read existing Mongo data still work.

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

1. Copy `code/Backend/credentials/backend_example.env` → `code/Backend/credentials/backend.env` and fill in API keys.
2. Configure `code/Backend/ai/AI.env` with `MONGO_URI` and `GROQ_API_KEY`.
3. Set `API_BASE` in `code/Frontend/ai_listening_tool/static/ai_listening_tool/js/config.js` to `http://127.0.0.1:8000/api`.

---

## Run commands

Start **Backend first**, then **Frontend**. Use two terminals with the shared venv activated.

| Service | Working directory | Command | URL |
|---------|-------------------|---------|-----|
| Backend (Flask) | `code/Backend` | `python app.py 8000` | `http://127.0.0.1:8000/api/health/` |
| Frontend (Django) | `code/Frontend` | `python manage.py runserver 8001` | `http://127.0.0.1:8001/tool/` |

```bash
# Terminal 1 — Backend
cd code/Backend
python app.py 8000

# Terminal 2 — Frontend
cd code/Frontend
python manage.py runserver 8001
```

Kafka was removed from this repo. Queuing uses **SQS** per `SYSTEM_ARCHITECTURE.md` (implementation pending — see `FUTURE_WORK.md`).

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
├── FUTURE_WORK.md                             # Deferred tasks (crawl API, Frontend, AI workers)
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
│   │   ├── cleanup_raw_insights.py            # Raw data cleanup utilities
│   │   └── views.py                           # Flask route handlers
│   ├── db/                                    # MongoDB helpers
│   │   ├── __init__.py
│   │   └── persist.py                         # History, company profiles, AI results writes
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
│   ├── workers/                               # Placeholder for future SQS AI consumer
│   │   └── README.md
│   ├── credentials/
│   │   ├── backend_example.env                # Template for backend.env
│   │   └── backend.env                        # Backend API keys and MongoDB URI (not committed)
│   └── tests/
│       └── __init__.py
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
| `Backend/credentials/backend.env` | `MONGODB_URI`, `NEWSAPI_KEY`, `SERPAPI_KEY` | Flask Backend (`config.py`) |
| `Backend/ai/AI.env` | `MONGO_URI`, `GROQ_API_KEY` | All AI modules |

### Setup

```bash
# Backend credentials
cp code/Backend/credentials/backend_example.env code/Backend/credentials/backend.env
# Edit backend.env with your API keys and MongoDB URI

# AI credentials — edit code/Backend/ai/AI.env directly
# Set MONGO_URI (same cluster as MONGODB_URI) and GROQ_API_KEY
```

**Critical:** Backend reads `MONGODB_URI`; AI reads `MONGO_URI`. Both must point to the same MongoDB cluster (`pace_database`).

---

## Key API endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health/` | GET | Health check |
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

### Agent search flow (legacy — blocked until Crawl Management API)

```
POST /api/search/  → 501 not_implemented (see FUTURE_WORK.md)
# After future crawl API lands:
# create crawl job → poll status → GET /api/results/ (or successor)
```

---

## Testing commands

```bash
# Backend health check (from code/Backend, venv activated)
cd code/Backend
python app.py 8000

curl -s http://127.0.0.1:8000/api/health/

# Search is stubbed (expect 501)
curl -s -X POST "http://127.0.0.1:8000/api/search/" \
  -H "Content-Type: application/json" \
  -d '{"subject":"Artificial Intelligence"}'

# Frontend page checks
curl -s http://127.0.0.1:8001/tool/
curl -s http://127.0.0.1:8001/tool/history/
curl -s http://127.0.0.1:8001/tool/results/
```

---

## Common pitfalls

- **Start Backend before Frontend.** The Frontend depends on `API_BASE` reaching the Backend.
- **`POST /api/search/` returns 501.** New searches are intentionally broken until the Crawl Management API lands (`FUTURE_WORK.md`).
- **Mismatched Mongo env vars.** Backend uses `MONGODB_URI` in `backend.env`; AI uses `MONGO_URI` in `AI.env`. Both must reference the same cluster.
- **Slow first AI run.** SBERT and spaCy models download on first use. Expect a long cold start.
- **Summarization vs Groq.** Search-result summaries are extractive (TF-IDF, no LLM). Groq is used only for `collection_card` features (ideas, competitors, news feed, etc.).
- **Do not commit credentials.** Use `backend_example.env` as a template. Real keys belong in `backend.env` and `AI.env`, which are gitignored.
- **Duplicate static files.** When editing Frontend JS/CSS, use the top-level `ai_listening_tool/static/` directory, not the nested `listening_tool/static/` copy.
- **Do not reintroduce Kafka or in-repo crawlers.** Use Data-Crawler-Task + SQS per architecture.
