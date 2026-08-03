from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
from pathlib import Path
import os
import sys

# Load environment variables from ai.env
env_path = Path(__file__).parent.parent / "AI.env"
load_dotenv(env_path)

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI not found in AI.env")
db = MongoClient(MONGO_URI)["pace_database"]

def main(hid: str):
    sample = db.ai_results.find_one(
        {"$or":[{"history_id":hid},{"history_id":ObjectId(hid)}], "status":"done"},
        {"raw_id":1,"url":1}
    )
    if not sample:
        print("No ai_results.done for that history.")
        return
    print("Sample ai_results:", sample)

    raw_id = sample.get("raw_id")
    url = sample.get("url")

    if raw_id:
        for coll in ["raw_insights","raw_articles","pages","crawler_pages","content_cache","articles_raw"]:
            doc = db[coll].find_one({"_id": raw_id}, {"_id":1})
            print(f"{coll} by raw_id:", "FOUND" if doc else "—")

    if url:
        for coll in ["raw_insights","raw_articles","pages","crawler_pages","content_cache","articles_raw"]:
            doc = db[coll].find_one({"url": url}, {"_id":1})
            print(f"{coll} by url:", "FOUND" if doc else "—")

if __name__ == "__main__":
    main(sys.argv[1])
