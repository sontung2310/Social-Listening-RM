# AI/ranking_algorithm/seed_ai_results.py
from pymongo import MongoClient, UpdateOne
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

# Change this if your raw text is elsewhere
RAW_COLLECTION = "raw_insights"  # e.g. "raw_articles" / "crawler_pages" / "content_cache"

def _hid_or(hid: str):
    ors = [{"history_id": hid}]
    try:
        ors.append({"history_id": ObjectId(hid)})
    except Exception:
        pass
    return {"$or": ors}

def main(hid: str):
    # ---- Path A: preferred — raw collection rows already tagged with history_id
    flt = _hid_or(hid)
    raws = list(db[RAW_COLLECTION].find(flt, {"_id":1,"url":1,"source":1,"published_ts":1}))
    if raws:
        ops = []
        for r in raws:
            ops.append(UpdateOne(
                {"history_id": hid, "url": r.get("url")},  # upsert key (avoid duplicating)
                {"$setOnInsert": {
                    "history_id": hid,
                    "raw_id": r["_id"],
                    "url": r.get("url"),
                    "source": r.get("source"),
                    "published_ts": r.get("published_ts"),
                    "status": "queued",
                }},
                upsert=True
            ))
        if ops:
            res = db.ai_results.bulk_write(ops, ordered=False)
            print(f"[OK] Seeded from {RAW_COLLECTION}: inserted={getattr(res,'upserted_count',0)}")
            return

    # ---- Path B: fallback — use ai_results(done/any) to discover raw_ids & seed queued
    print(f"[WARN] No raw data tagged with history_id in {RAW_COLLECTION}. Falling back to ai_results…")
    ai_rows = list(db.ai_results.find(_hid_or(hid), {"raw_id":1,"url":1,"source":1,"published_ts":1}))
    if not ai_rows:
        print(f"[WARN] No ai_results found for history_id={hid}. Nothing to seed.")
        return

    # join to RAW_COLLECTION by raw_id (preferred) or by url as fallback
    ops = []
    for a in ai_rows:
        raw = None
        rid = a.get("raw_id")
        if rid:
            raw = db[RAW_COLLECTION].find_one({"_id": rid}, {"_id":1,"url":1,"source":1,"published_ts":1})
        if not raw and a.get("url"):
            raw = db[RAW_COLLECTION].find_one({"url": a["url"]}, {"_id":1,"url":1,"source":1,"published_ts":1})

        if not raw:
            continue

        ops.append(UpdateOne(
            {"history_id": hid, "url": raw.get("url")},
            {"$setOnInsert": {
                "history_id": hid,
                "raw_id": raw["_id"],
                "url": raw.get("url"),
                "source": raw.get("source"),
                "published_ts": raw.get("published_ts"),
                "status": "queued",
            }},
            upsert=True
        ))

    if not ops:
        print(f"[WARN] Couldn’t map ai_results to {RAW_COLLECTION}. Check that raw text lives in '{RAW_COLLECTION}'.")
        return

    res = db.ai_results.bulk_write(ops, ordered=False)
    print(f"[OK] Seeded from ai_results fallback: inserted={getattr(res,'upserted_count',0)}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m AI.ranking_algorithm.seed_ai_results <history_id>")
        sys.exit(1)
    main(sys.argv[1])
