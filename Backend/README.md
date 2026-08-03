# Setup Guide

Follow the steps below to set up and run the **PACE Discovery Bot Backend** locally.

---

## 1.  Clone Repository

```bash
git clone <your-repo-url>
cd code/Backend
```

## 2.  Create and Activate Virtual Environment

```bash
python -m venv .venv
```

```bash
Open 2 Terminals. Terminal 1 & 2

# Windows
.venv/Scripts/activate

# macOS / Linux
source .venv/bin/activate
```

## 3.  Install Dependencies
```bash
pip install -r requirements.txt
```


## 4.  Run the Server
```bash
Terminal 1

python app.py 8000
```

## Notes
- Ensure your MongoDB cluster and API keys are valid before running the server (`credentials/backend.env` + `ai/AI.env`).
- The default port 8000 can be changed if needed.
- All environment variables must be set before launching the flask server.
- `POST /api/search/` currently returns **501** — crawl ingest moved to Data-Crawler-Task; see `code/FUTURE_WORK.md`.


## Quick testing

## `/api/health/`
```bash
Terminal 2

# Windows
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health/" -Method GET |
  ConvertTo-Json -Depth 10

# macOS / Linux
curl -s http://127.0.0.1:8000/api/health/ | jq .
```

## `/api/search/`
```bash
Terminal 2

# Windows
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/search/" -Method POST `
-Body '{"subject":"Artificial Intelligence"}' -ContentType "application/json" |
ConvertTo-Json -Depth 10


# macOS / Linux
curl -s -X POST "http://127.0.0.1:8000/api/search/" \
  -H "Content-Type: application/json" \
  -d '{"subject":"Artificial Intelligence"}' | jq .
```

## `/api/debug/mongo/`
```bash
Terminal 2

# Windows
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/debug/mongo/" -Method GET |
  ConvertTo-Json -Depth 10


# macOS / Linux
curl -s http://127.0.0.1:8000/api/debug/mongo/ | jq .
```

## `/api/history/`
```bash
Terminal 2

# Windows
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/history/?limit=20" -Method GET |
  ConvertTo-Json -Depth 10

# macOS / Linux
curl -s "http://127.0.0.1:8000/api/history/?limit=20" | jq .
```

## `/api/search/status/`
```bash
Terminal 2

# Windows
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/search/status/?history_id=<HISTORY_ID>" -Method GET | ConvertTo-Json -Depth 10

# macOS / Linux
curl -s "http://127.0.0.1:8000/api/search/status/?history_id=<HISTORY_ID>" | jq .
```

## `/api/results/`
```bash
Terminal 2
# Windows
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/results/?history_id=<HISTORY_ID>&status=done&page=1&page_size=10" -Method GET | ConvertTo-Json -Depth 10

# macOS / Linux
curl -s "http://127.0.0.1:8000/api/results/?history_id=<HISTORY_ID>&status=done&page=1&page_size=10" | jq .
```

## `/api/trends/`
```bash
Terminal 2
# Windows
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/trends/?history_id=<HISTORY_ID>&days=30" -Method GET |
  ConvertTo-Json -Depth 10

# macOS / Linux
curl -s "http://127.0.0.1:8000/api/trends/?history_id=<HISTORY_ID>&days=30" | jq .
```

## `/api/topics/top/`
```bash
Terminal 2
# Windows
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/topics/top/?days=30&limit=15" -Method GET |
  ConvertTo-Json -Depth 10

# macOS / Linux
curl -s "http://127.0.0.1:8000/api/topics/top/?days=30&limit=15" | jq .
```

## `/api/company/`
```bash
Terminal 2
# Windows
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/company/?name=Tesla" -Method GET |
  ConvertTo-Json -Depth 10

# macOS / Linux
curl -s "http://127.0.0.1:8000/api/company/?name=Tesla" | jq .
```

# Cards
## `/api/cards/trending/`
```bash
Terminal 2
# Windows 
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/cards/trending/?company_id=69072b397c33c037fd2da784&threshold=0.5&limit=10&full=1" -Method GET |
  ConvertTo-Json -Depth 10

# macOS / Linux
curl -s "http://127.0.0.1:8000/api/cards/trending/?company_id=69072b397c33c037fd2da784&threshold=0.5&limit=10&full=1" | jq .
```

## `/api/cards/newsfeed/`
```bash
Terminal 2
# Windows 
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/cards/newsfeed/?company_id=69072b397c33c037fd2da784&threshold=0.5&limit=10&full_analysis=1" -Method GET |
  ConvertTo-Json -Depth 10

# macOS / Linux
curl -s "http://127.0.0.1:8000/api/cards/newsfeed/?company_id=69072b397c33c037fd2da784&threshold=0.5&limit=10&full_analysis=1" | jq .
```

## `/api/ai/ideas/`
```bash
Terminal 2
# Windows
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/ai/ideas/?company=Tesla=all&limit=10" -Method GET |
  ConvertTo-Json -Depth 10

# macOS / Linux
curl -s "http://127.0.0.1:8000/api/ai/ideas/?company=Tesla=all&limit=10" | jq .
```

## `/api/ai/competitors/`
```bash
Terminal 2
# Windows (PowerShell)
$body = @{
  text       = "We build EV fast chargers for fleets and retail."
  seed_brand = "EcoDrive Motors"
  industry   = @("EV","Charging","Energy")
  location   = @("Australia","New South Wales")
  top_n      = 5
  min_score  = 0.25
  verbose    = $false
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/ai/competitors/" -Method POST `
  -ContentType "application/json" -Body $body |
  ConvertTo-Json -Depth 10

# macOS / Linux
curl -s -X POST "http://127.0.0.1:8000/api/ai/competitors/" \
  -H "Content-Type: application/json" \
  -d '{
    "text":"We build EV fast chargers for fleets and retail.",
    "seed_brand":"EcoDrive Motors",
    "industry":["EV","Charging","Energy"],
    "location":["Australia","New South Wales"],
    "top_n":5,
    "min_score":0.25,
    "verbose":false
  }' | jq .
```

## `/api/ai/backlinks/`
```bash
Terminal 2
# Windows
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/ai/backlinks/?company=Tesla&limit=50&no_llm=0&return_stored=0" -Method GET |
  ConvertTo-Json -Depth 10

# macOS / Linux
curl -s "http://127.0.0.1:8000/api/ai/backlinks/?company=Tesla&limit=50&no_llm=0&return_stored=0" | jq .
```

## `/api/company/upsert/`
```bash
Terminal 2
# Windows
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/company/upsert/" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body | ConvertTo-Json -Depth 10

# macOS / Linux
curl -s -X POST "http://127.0.0.1:8000/api/company/upsert/" \
  -H "Content-Type: application/json" \
  -d '{"name":"EcoDrive Motors","description":"EV charging","competitors":["VoltX","ChargeCo"]}' | jq .
```

## `/api/companies/`
```bash
Terminal 2
# Windows
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/companies/?page=1&page_size=20&q=EV&sort=name&order=asc" `
  -Method GET | ConvertTo-Json -Depth 10

# macOS / Linux
curl -s -X POST "http://127.0.0.1:8000/api/ai/competitors/" \
  -H "Content-Type: application/json" \
  -d '{
    "text":"We build EV fast chargers for fleets.",
    "seed_brand":"EcoDrive Motors",
    "industry":["EV","Charging","Energy"],
    "location":["Australia","NSW"],
    "top_n":5,
    "min_score":0.25
  }' | jq .
```


## API Endpoints

| Endpoint                   | Method | Description |
| --------------------------- | ------ | ------------ |
| `/api/health/`              | GET    | Check if the backend server is running and healthy |
| `/api/search/`              | POST   | **501 stub** — crawl ingest moved to Data-Crawler-Task (`FUTURE_WORK.md`) |
| `/api/history/`             | GET    | List previously run searches with metadata (subject, date, AI status) |
| `/api/search/status/`       | GET    | Check the AI processing progress for a given `history_id` |
| `/api/results/`             | GET    | Retrieve paginated AI-generated results for a given `history_id` |
| `/api/trends/`              | GET    | Get timeseries trends, top tags, and source breakdown for a `history_id` |
| `/api/topics/top/`          | GET    | Retrieve global trending topics (simple topic list) |
| `/api/debug/mongo/`         | GET    | Show MongoDB collection names and document counts for debugging |
| `/api/company/`             | GET    | Retrieve the latest or specific company profile (name, description, competitors) |
| `/api/cards/trending/`      | GET    | Generate company-aware trending topics using the AI relevancy model |
| `/api/cards/newsfeed/`      | GET    | Generate AI-ranked news feed for a given company  |
| `/api/ai/ideas/`            | GET    | Generate AI-powered idea suggestions based on company insights |
| `/api/ai/competitors/`      | POST   | Identify competitor brands from a given text or context using AI |
| `/api/ai/backlinks/`        | GET    | Retrieve backlinks and sources related to a company       |
| `/api/ai/opportunities/`    | GET    | Generate business opportunities related to a company and industry |
| `/api/company/upsert/`    | POST    | Create or update (upsert) a company profile |
| `/api/companies/`    | GET    | List companies |

---

