# AI/ranking_algorithm/backfill_sentiment.py
"""
Backfill sentiment analysis for existing ai_results documents that don't have it.
"""
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
from pathlib import Path
import os
import sys

# Load environment variables from ai.env
env_path = Path(__file__).parent.parent / "AI.env"
load_dotenv(env_path)

# Import sentiment analyzer
from ai.sentiment_analysis.sentiment_analyzer import quick_sentiment

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI not found in AI.env")
client = MongoClient(MONGO_URI)
db = client["pace_database"]

# Collections that might contain raw text
RAW_COLLECTIONS = [
    "raw_insights",
    "raw_articles",
    "crawler_pages",
    "content_cache",
    "pages",
    "articles_raw",
]


def get_text_for_doc(ai_doc):
    """
    Try to find text for this ai_results document.
    Strategy: raw_id -> url lookup -> fallback to ai_summary+ai_title
    """
    raw_id = ai_doc.get("raw_id")
    url = ai_doc.get("url")

    # Try raw collections
    for coll_name in RAW_COLLECTIONS:
        if raw_id:
            try:
                raw = db[coll_name].find_one({"_id": raw_id}, {"text": 1})
                if raw and raw.get("text"):
                    return raw["text"]
            except Exception:
                pass

        if url:
            raw = db[coll_name].find_one({"url": url}, {"text": 1})
            if raw and raw.get("text"):
                return raw["text"]

    # Fallback: reconstruct from ai_results
    parts = [
        ai_doc.get("ai_title", ""),
        ai_doc.get("ai_summary", ""),
        ai_doc.get("text", "")
    ]
    text = "\n".join(p for p in parts if p).strip()
    return text or None


def backfill_sentiment(history_id=None, limit=None, dry_run=False):
    """
    Backfill sentiment for ai_results documents missing the field.

    Args:
        history_id: Optional - only process this history_id
        limit: Optional - max number of documents to process
        dry_run: If True, don't write to database (just print)
    """
    # Build query for documents missing sentiment
    query = {"sentiment": {"$exists": False}, "status": "done"}

    if history_id:
        try:
            query["history_id"] = ObjectId(history_id)
        except:
            query["history_id"] = history_id

    # Count total
    total = db.ai_results.count_documents(query)
    print(f"[INFO] Found {total} documents without sentiment field")

    if total == 0:
        print("[OK] All documents already have sentiment!")
        return

    # Fetch documents
    cursor = db.ai_results.find(query, {"_id": 1, "url": 1, "raw_id": 1, "ai_title": 1, "ai_summary": 1, "text": 1})

    if limit:
        cursor = cursor.limit(limit)
        print(f"[INFO] Processing first {limit} documents (use limit=None for all)")

    # Process each document
    processed = 0
    skipped = 0
    errors = 0

    for doc in cursor:
        try:
            # Get text
            text = get_text_for_doc(doc)

            if not text:
                print(f"[WARN] No text found for {doc.get('url')} - skipping")
                skipped += 1
                continue

            # Analyze sentiment
            sentiment = quick_sentiment(text, method='vader')

            if dry_run:
                print(f"[DRY RUN] Would set sentiment={sentiment} for {doc.get('url')}")
            else:
                # Update document
                db.ai_results.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"sentiment": sentiment}}
                )
                print(f"[OK] Updated {doc.get('url')} -> sentiment={sentiment}")

            processed += 1

        except Exception as e:
            print(f"[ERROR] Failed to process {doc.get('url')}: {e}")
            errors += 1

    print(f"\n[SUMMARY]")
    print(f"  Processed: {processed}")
    print(f"  Skipped (no text): {skipped}")
    print(f"  Errors: {errors}")
    print(f"  Total: {total}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Backfill sentiment analysis for existing ai_results")
    parser.add_argument("--history-id", help="Only process this history_id")
    parser.add_argument("--limit", type=int, help="Max documents to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB, just print")

    args = parser.parse_args()

    backfill_sentiment(
        history_id=args.history_id,
        limit=args.limit,
        dry_run=args.dry_run
    )
