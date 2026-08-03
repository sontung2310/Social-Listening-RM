from bson import ObjectId
from pymongo import MongoClient
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

def fetch_articles(history_id: str):
    history_id = ObjectId(history_id)

    queued = list(db.ai_results.find(
        {"history_id": history_id},
        {"url": 1, "raw_id": 1, "source": 1, "published_ts": 1}
    ))

    docs = []
    for q in queued:
        raw = db.raw_insights.find_one({"_id": q["raw_id"]}, {"text": 1, "engagement": 1})
        if raw and raw.get("text"):
            docs.append({
                "_id": q["raw_id"],
                "text": raw["text"],
                "engagement": raw.get("engagement", {}),
                "source": q["source"],
                "published_ts": q["published_ts"],
                "url": q["url"],
            })
    return docs