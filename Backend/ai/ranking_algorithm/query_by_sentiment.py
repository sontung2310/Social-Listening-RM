# AI/ranking_algorithm/query_by_sentiment.py
"""
Example queries for filtering ai_results by sentiment.
"""
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
from pathlib import Path
import os

# Load environment variables from ai.env
env_path = Path(__file__).parent.parent / "AI.env"
load_dotenv(env_path)

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI not found in AI.env")
db = MongoClient(MONGO_URI)["pace_database"]


def get_by_sentiment(history_id, sentiment_filter=None, include_unknown=True):
    """
    Fetch ai_results for a history_id, optionally filtered by sentiment.

    Args:
        history_id: The history_id to query
        sentiment_filter: 'positive', 'negative', 'neutral', or None (all)
        include_unknown: If True, include documents without sentiment field

    Returns:
        List of matching documents
    """
    try:
        hid = ObjectId(history_id)
    except:
        hid = history_id

    query = {
        "$or": [{"history_id": hid}, {"history_id": str(hid)}],
        "status": "done"
    }

    # Add sentiment filter
    if sentiment_filter:
        if include_unknown:
            # Include documents where sentiment matches OR doesn't exist
            query["$and"] = [
                {
                    "$or": [
                        {"sentiment": sentiment_filter},
                        {"sentiment": {"$exists": False}},
                        {"sentiment": None}
                    ]
                }
            ]
        else:
            # Only exact matches
            query["sentiment"] = sentiment_filter

    results = list(db.ai_results.find(query).sort([("relevance_score", -1)]))

    return results


def get_sentiment_breakdown(history_id):
    """
    Get count of documents by sentiment for a history_id.

    Returns:
        Dict with counts: {'positive': 10, 'negative': 5, 'neutral': 3, 'unknown': 2}
    """
    try:
        hid = ObjectId(history_id)
    except:
        hid = history_id

    pipeline = [
        {
            "$match": {
                "$or": [{"history_id": hid}, {"history_id": str(hid)}],
                "status": "done"
            }
        },
        {
            "$group": {
                "_id": {
                    "$ifNull": ["$sentiment", "unknown"]
                },
                "count": {"$sum": 1}
            }
        }
    ]

    results = list(db.ai_results.aggregate(pipeline))

    breakdown = {r["_id"]: r["count"] for r in results}
    return breakdown


def get_only_positive_articles(history_id):
    """Get only positive sentiment articles"""
    return get_by_sentiment(history_id, sentiment_filter="positive", include_unknown=False)


def get_only_negative_articles(history_id):
    """Get only negative sentiment articles"""
    return get_by_sentiment(history_id, sentiment_filter="negative", include_unknown=False)


def get_only_neutral_articles(history_id):
    """Get only neutral sentiment articles"""
    return get_by_sentiment(history_id, sentiment_filter="neutral", include_unknown=False)


if __name__ == "__main__":
    # Example usage
    history_id = "68fdda1caf9de874acb5a32a"

    print("=== Sentiment Breakdown ===")
    breakdown = get_sentiment_breakdown(history_id)
    for sentiment, count in breakdown.items():
        print(f"{sentiment}: {count}")

    print("\n=== Positive Articles (Top 5) ===")
    positive = get_only_positive_articles(history_id)
    for doc in positive[:5]:
        print(f"- {doc.get('ai_title')} ({doc.get('url')})")

    print("\n=== All Articles (including unknown sentiment) ===")
    all_docs = get_by_sentiment(history_id, include_unknown=True)
    print(f"Total: {len(all_docs)}")
