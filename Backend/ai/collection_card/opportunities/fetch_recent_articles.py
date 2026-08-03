# AI/collection_card/opportunities/fetch_recent_articles.py
"""
Fetch articles for a specific history_id from ai_results collection.
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


def fetch_articles_by_history_id(
    history_id: str,
    limit: int = 10,
    include_sentiment: bool = True
) -> List[Dict[str, Any]]:
    """
    Fetch top N articles for a specific history_id from ai_results collection.
    Sorted by relevance_score (descending) to get the most relevant articles.

    Args:
        history_id: The history ID to fetch articles for
        limit: Number of top articles to fetch (default: 10)
        include_sentiment: Include sentiment field in results (default: True)

    Returns:
        List of article dictionaries sorted by relevance
    """
    # Build projection (fields to include)
    projection = {
        "_id": 0,
        "url": 1,
        "ai_title": 1,
        "ai_summary": 1,
        "source": 1,
        "relevance_score": 1,
        "published_ts": 1,
        "tags": 1,
        "rank": 1,
    }

    if include_sentiment:
        projection["sentiment"] = 1

    # Query filter - fetch articles for this history_id with status "done"
    query = {
        "history_id": ObjectId(history_id),
        "status": "done"
    }

    # Fetch articles sorted by published_ts (most recent first)
    cursor = db.ai_results.find(query, projection).sort([("published_ts", -1)]).limit(limit)

    articles = list(cursor)

    # Add default sentiment if missing
    if include_sentiment:
        for article in articles:
            if "sentiment" not in article or article["sentiment"] is None:
                article["sentiment"] = "neutral"

    return articles
