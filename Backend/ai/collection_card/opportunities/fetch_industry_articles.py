# AI/collection_card/fetch_industry_articles.py

from __future__ import annotations

from pymongo import MongoClient
from typing import List, Dict, Any
from dotenv import load_dotenv
from pathlib import Path
import os
import re
import time

# Load environment variables from ai.env
env_path = Path(__file__).parent.parent.parent / "AI.env"
load_dotenv(env_path)

# Mongo connection
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI not found in AI.env")
client = MongoClient(MONGO_URI)
db = client["pace_database"]


def _industry_regex(industry_name: str) -> Dict[str, Any]:
    """
    Escape special chars and allow flexible whitespace between tokens.
    """
    if not industry_name:
        return {}
    escaped = re.escape(industry_name.strip())
    flexible = re.sub(r"\\\s+", r"\\s+", escaped)
    return {"$regex": flexible, "$options": "i"}


def _industry_match_or(industry_name: str) -> Dict[str, Any]:
    """
    Build an $or filter over title, summary, source, and tags (with $elemMatch).
    """
    if not industry_name:
        return {}
    rx = _industry_regex(industry_name)
    return {
        "$or": [
            {"ai_title": rx},
            {"ai_summary": rx},
            {"source": rx},
            {"tags": {"$elemMatch": rx}},  # correct way to regex-match inside arrays
        ]
    }


def _normalize_articles(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ensure consistent keys and sane defaults for downstream LLM.
    - Provide both 'url' and 'uri' (alias).
    - Ensure published_ts exists.
    - Keep only the fields we care about.
    """
    now_ts = int(time.time())
    out: List[Dict[str, Any]] = []
    for r in rows:
        url = r.get("url") or r.get("uri") or ""
        ai_title = r.get("ai_title") or ""
        ai_summary = r.get("ai_summary") or ""
        source = r.get("source") or ""
        relevance = float(r.get("relevance_score", 0.0))
        published_ts = (
            r.get("published_ts") if r.get("published_ts") is not None else now_ts
        )
        tags = r.get("tags", [])

        out.append(
            {
                "ai_title": ai_title,
                "ai_summary": ai_summary,
                "url": url,
                "uri": url,  # alias so other modules don't break
                "source": source,
                "relevance_score": relevance,
                "published_ts": int(published_ts),
                "tags": tags,
            }
        )
    return out


def _dedupe_by_key(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Dedupe by (uri or ai_title).
    """
    seen = set()
    out = []
    for r in rows:
        key = (r.get("uri") or r.get("ai_title") or "").strip().lower()
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _query_ai_results(filter_: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    cur = (
        db.ai_results.find(
            filter_,
            {
                "_id": 0,
                "ai_title": 1,
                "ai_summary": 1,
                "url": 1,  # store as url, we'll also alias to uri
                "source": 1,
                "relevance_score": 1,
                "published_ts": 1,
                "tags": 1,
            },
        )
        .sort([("published_ts", -1), ("relevance_score", -1)])
        .limit(int(limit))
    )
    return list(cur)


def get_industry_articles(
    industry_name: str, limit: int = 20, min_relevance: float = 0.4
) -> List[Dict[str, Any]]:
    """
    Fetch recent high-relevance articles for a given industry/sector/topic.

    Strategy (robust to sparse data):
      1) Strict industry match + min_relevance
      2) If too few, relax relevance to 0.2
      3) If still too few, drop the industry filter and pull recent generic relevant articles
    """
    limit = max(1, int(limit))
    base_filter = {"status": "done", "relevance_score": {"$gte": float(min_relevance)}}
    ind_filter = _industry_match_or(industry_name)

    # Pass 1: strict
    strict_filter = {**base_filter, **ind_filter}
    rows = _query_ai_results(strict_filter, limit)
    articles = _normalize_articles(rows)

    if len(articles) >= limit // 2:
        return _dedupe_by_key(articles)[:limit]

    # Pass 2: relaxed relevance
    relaxed_filter = {"status": "done", "relevance_score": {"$gte": 0.2}, **ind_filter}
    rows_relaxed = _query_ai_results(relaxed_filter, limit)
    articles_relaxed = _normalize_articles(rows_relaxed)
    merged = _dedupe_by_key(articles + articles_relaxed)
    if len(merged) >= limit // 2:
        return merged[:limit]

    # Pass 3: generic recent relevant (no industry filter), just to give LLM context
    generic_filter = {"status": "done", "relevance_score": {"$gte": 0.25}}
    rows_generic = _query_ai_results(generic_filter, limit)
    articles_generic = _normalize_articles(rows_generic)

    final = _dedupe_by_key(merged + articles_generic)[:limit]
    return final
