# AI/shared/fetch_articles.py
from __future__ import annotations
from typing import List, Dict, Any
from dotenv import load_dotenv
from pathlib import Path
import os
import time
from bson import ObjectId
from pymongo import MongoClient

# Load environment variables from ai.env
env_path = Path(__file__).parent.parent / "AI.env"
load_dotenv(env_path)

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI not found in AI.env")
client = MongoClient(MONGO_URI)
db = client["pace_database"]


def get_company_by_id(company_id: str) -> Dict[str, Any] | None:
    """
    Return a minimal company profile by ID.
    Expects collection: company_profiles
    """
    try:
        oid = ObjectId(company_id)
    except Exception:
        return None

    doc = db.company_profiles.find_one(
        {"_id": oid},
        {"_id": 1, "name": 1, "description": 1, "competitors": 1}
    )
    if not doc:
        return None

    return {
        "company_id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "description": doc.get("description", ""),
        "competitors": doc.get("competitors", []),
    }


def get_company_articles(
    company_id: str,
    *,
    limit: int = 50,
    min_relevance: float = 0.30
) -> List[Dict[str, Any]]:
    """
    Fetch recent, relevant AI-enriched articles for a given company.

    Preferred schema in ai_results:
      - company_id: ObjectId of company_profiles._id  (recommended)
      - status: "done"
      - relevance_score: float
      - ai_title, ai_summary, url, source, published_ts, tags

    Falls back to matching by company name if company_id linkage is not present.
    """
    profile = get_company_by_id(company_id)
    if not profile:
        return []

    # Build the primary query (by company_id)
    try:
        oid = ObjectId(company_id)
    except Exception:
        return []

    query_primary: Dict[str, Any] = {
        "status": "done",
        "relevance_score": {"$gte": float(min_relevance)},
        "company_id": oid,
    }

    projection = {
        "_id": 0,
        "ai_title": 1,
        "ai_summary": 1,
        "url": 1,                # use 'url' consistently
        "source": 1,
        "relevance_score": 1,
        "published_ts": 1,
        "tags": 1,
    }

    cursor = db.ai_results.find(query_primary, projection).sort(
        [("published_ts", -1), ("relevance_score", -1)]
    ).limit(int(limit))
    articles = list(cursor)

    # Fallback: if nothing linked by company_id, try a name-based heuristic
    if not articles and profile["name"]:
        name = profile["name"]
        query_fallback = {
            "status": "done",
            "relevance_score": {"$gte": float(min_relevance)},
            "$or": [
                {"ai_title":   {"$regex": name, "$options": "i"}},
                {"ai_summary": {"$regex": name, "$options": "i"}},
                {"source":     {"$regex": name, "$options": "i"}},
                {"tags":       {"$elemMatch": {"$regex": name, "$options": "i"}}},
            ],
        }
        cursor = db.ai_results.find(query_fallback, projection).sort(
            [("published_ts", -1), ("relevance_score", -1)]
        ).limit(int(limit))
        articles = list(cursor)

    # Ensure published_ts exists (helps downstream sort/LLM context)
    now_ts = int(time.time())
    for a in articles:
        if not a.get("published_ts"):
            a["published_ts"] = now_ts

    return articles
