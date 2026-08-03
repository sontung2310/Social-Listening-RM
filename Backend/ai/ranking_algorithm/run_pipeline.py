# AI/ranking_algorithm/run_pipeline.py
from ai.ranking_algorithm.seed_ai_results import main as seed_once
from ai.ranking_algorithm.check_history import clauses
from ai.ranking_algorithm.main import run as rank_run
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

def run_pipeline(history_id: str, keyword: str):
    # 1) If there are no queued rows for this history, seed them
    hid_clause = clauses(history_id)
    has_queued = db.ai_results.count_documents({**hid_clause, "status":"queued"}) > 0
    if not has_queued:
        seed_once(history_id)  # will create queued items from raw_* using url/raw_id

    # 2) Run ranking + summarization
    return rank_run(history_id, keyword)
