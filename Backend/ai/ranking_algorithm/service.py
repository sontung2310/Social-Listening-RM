# AI/ranking_algorithm/service.py
from __future__ import annotations
from typing import Dict, Any, List
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path
import os

# Load environment variables from ai.env
env_path = Path(__file__).parent.parent / "AI.env"
load_dotenv(env_path)

# Reuse your existing modules
from ai.ranking_algorithm.seed_ai_results import main as seed_ai_results
from ai.ranking_algorithm.main import run as run_pipeline
from ai.ranking_algorithm.check_history import clauses as build_history_clauses

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI not found in AI.env")
db = MongoClient(MONGO_URI)["pace_database"]

def run_full_pipeline(history_id: str, keyword: str, sentiment_filter: str = None) -> Dict[str, Any]:
    """
    1) Seed queued rows (robust fallback inside seed_ai_results)
    2) Run ranking pipeline (summarize + topic detection + write ai_results)
    3) Return a structured summary for the frontend

    Args:
        history_id: The search history ID
        keyword: Search keyword
        sentiment_filter: Optional - filter results by 'positive', 'negative', 'neutral'
    """
    # Seed (no raise if nothing to seed)
    seed_ai_results(history_id)

    # Run main pipeline (returns rows for debugging; writes ai_results)
    rows = run_pipeline(history_id, keyword) or []

    # Recount
    cl = build_history_clauses(history_id)
    raw_cnt = db.raw_insights.count_documents(cl)
    queued  = db.ai_results.count_documents({**cl, "status": "queued"})
    done    = db.ai_results.count_documents({**cl, "status": "done"})

    # Fetch top results to display immediately
    top_query = {**cl, "status": "done"}

    # Optional sentiment filter
    if sentiment_filter and sentiment_filter in ['positive', 'negative', 'neutral']:
        top_query["sentiment"] = sentiment_filter

    top = list(db.ai_results.find(top_query)
               .sort([("relevance_score", -1)])
               .limit(25))

    # Clean up a bit for API response
    def _trim(doc):
        return {
            "url": doc.get("url"),
            "rank": doc.get("rank"),
            "relevance_score": doc.get("relevance_score"),
            "engagement_score": doc.get("engagement_score", 0.0),  # Include engagement score
            "ai_title": doc.get("ai_title"),
            "ai_summary": doc.get("ai_summary"),
            "tags": doc.get("tags") or [],
            "sentiment": doc.get("sentiment") or "unknown",  # Default to "unknown" for old docs
            "source": doc.get("source"),
            "published_ts": doc.get("published_ts"),
        }

    return {
        "history_id": history_id,
        "keyword": keyword,
        "counts": {
            "raw_insights": raw_cnt,
            "ai_results": {"queued": queued, "done": done},
        },
        "processed": len(rows),
        "top_results": [_trim(t) for t in top],
    }
