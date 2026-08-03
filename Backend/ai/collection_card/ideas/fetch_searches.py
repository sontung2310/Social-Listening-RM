# AI/collection_card/ideas/fetch_searches.py
"""
Fetch recent searches and their top articles for idea generation.
"""

from pymongo import MongoClient
from typing import List, Dict, Any
from bson import ObjectId
from dotenv import load_dotenv
from pathlib import Path
import os

# Load environment variables from ai.env
env_path = Path(__file__).parent.parent.parent / "AI.env"
load_dotenv(env_path)

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI not found in AI.env")
client = MongoClient(MONGO_URI)
db = client["pace_database"]


def fetch_recent_searches(limit: int = 10) -> List[str]:
    """
    Fetch the last N unique history_ids (searches) from ai_results.
    Returns list of history_id strings, sorted by most recent.

    Args:
        limit: Number of recent searches to fetch (default: 10)

    Returns:
        List of history_id strings
    """
    # Use aggregation to get distinct history_ids ordered by most recent
    pipeline = [
        {"$match": {"status": "done", "history_id": {"$exists": True}}},
        {"$sort": {"created_at": -1}},
        {"$group": {
            "_id": "$history_id",
            "latest_created": {"$first": "$created_at"}
        }},
        {"$sort": {"latest_created": -1}},
        {"$limit": limit}
    ]

    results = list(db.ai_results.aggregate(pipeline))
    history_ids = [str(result["_id"]) for result in results]

    return history_ids


def fetch_top_articles_by_history(
    history_id: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Fetch top N articles for a specific history_id.
    Sorted by relevance_score to get the best articles from this search.
    Joins with raw_insights to get full article text.

    Args:
        history_id: The history ID to fetch articles for
        limit: Number of top articles to fetch (default: 10)

    Returns:
        List of article dictionaries with full text
    """
    projection = {
        "url": 1,
        "ai_title": 1,
        "ai_summary": 1,
        "source": 1,
        "relevance_score": 1,
        "published_ts": 1,
        "tags": 1,
        "sentiment": 1,
        "raw_id": 1,
    }

    query = {
        "history_id": ObjectId(history_id),
        "status": "done"
    }

    # Get top articles by relevance for this search
    cursor = db.ai_results.find(query, projection).sort([("relevance_score", -1)]).limit(limit)
    ai_results = list(cursor)

    # Join with raw_insights to get full text
    articles = []
    for result in ai_results:
        raw_id = result.get("raw_id")
        if not raw_id:
            continue

        # Fetch full text from raw_insights
        raw = db.raw_insights.find_one({"_id": raw_id}, {"text": 1})
        if not raw or not raw.get("text"):
            continue

        # Combine data from both collections
        article = {
            "url": result.get("url", ""),
            "ai_title": result.get("ai_title", ""),
            "ai_summary": result.get("ai_summary", ""),
            "text": raw["text"],  # Full article text
            "source": result.get("source", ""),
            "relevance_score": result.get("relevance_score", 0),
            "published_ts": result.get("published_ts", 0),
            "tags": result.get("tags", []),
            "sentiment": result.get("sentiment", "neutral"),
        }

        articles.append(article)

    return articles


def fetch_all_articles_for_ideas(
    num_searches: int = 10,
    articles_per_search: int = 10
) -> List[Dict[str, Any]]:
    """
    Fetch articles from the last N searches, getting top M articles per search.
    Returns deduplicated list of all articles combined.

    Args:
        num_searches: Number of recent searches to include (default: 10)
        articles_per_search: Number of top articles per search (default: 10)

    Returns:
        List of article dictionaries, deduplicated by URL
    """
    # Get recent searches
    history_ids = fetch_recent_searches(limit=num_searches)

    if not history_ids:
        return []

    # Collect articles from all searches
    all_articles = []
    seen_urls = set()

    for history_id in history_ids:
        articles = fetch_top_articles_by_history(history_id, limit=articles_per_search)

        # Deduplicate by URL
        for article in articles:
            url = article.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_articles.append(article)

    return all_articles
