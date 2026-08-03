from __future__ import annotations
import argparse
from typing import Dict, Any, List, Tuple
from bson import ObjectId
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path
import os
import re

# Load environment variables from ai.env
env_path = Path(__file__).parent.parent / "AI.env"
load_dotenv(env_path)

# --- Mongo Setup ---
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI not found in AI.env")
client = MongoClient(MONGO_URI)
db = client["pace_database"]

# --- Scoring Algorithms ---
from ai.ranking_algorithm.tf_idf_scorer import score_tfidf_simple
from ai.ranking_algorithm.bm25_scorer import BM25Scorer, minmax_normalize
from ai.ranking_algorithm.sbert_scorer import sbert_score_one
from ai.ranking_algorithm.engagement_scorer import engagement_score
from ai.ranking_algorithm.word_count_penalty import apply_word_count_penalty

# --- Summarization + Topic Detection ---
from ai.Topic_detection.Topic_detection import detect_topic_simple, detect_topics
from ai.Text_summarisation.main_summaries import generate_summary
from ai.ranking_algorithm.check_history import clauses

# --- Sentiment Analysis ---
from ai.sentiment_analysis.sentiment_analyzer import quick_sentiment

# --- Write Results to ai_results ---
from ai.ranking_algorithm.mongo import write_ai_results_batch

TOPK = 200

ALGORITHMS = {
    "tfidf": lambda keyword, doc: score_tfidf_simple(keyword, doc),
    "sbert": lambda keyword, doc: sbert_score_one(keyword, doc),
    "engagement": lambda keyword, doc: engagement_score(doc),
}

DEFAULT_WEIGHTS = {
    "bm25": 0.25,
    "sbert": 0.60,
    "engagement": 0.15,
    "tfidf": 0.05,
}

# ---------------------------------------------------------------------------
# RAW lookups
# ---------------------------------------------------------------------------
RAW_COLLECTIONS = [
    "raw_insights", "raw_articles", "crawler_pages",
    "content_cache", "pages", "articles_raw",
]

def _get_raw_doc_by_ref(db, raw_id, url):
    proj = {"text": 1, "engagement": 1}
    for coll in RAW_COLLECTIONS:
        if raw_id:
            try:
                doc = db[coll].find_one({"_id": raw_id}, proj)
                if doc and doc.get("text"):
                    return doc
            except Exception:
                pass
        if url:
            doc = db[coll].find_one({"url": url}, proj)
            if doc and doc.get("text"):
                return doc
    return None



def fetch_docs(history_id: str):
    queued = list(db.ai_results.find(
        {"$or":[{"history_id":history_id},{"history_id":ObjectId(history_id)}], "status":"queued"},
        {"url":1,"raw_id":1,"source":1,"published_ts":1}
    ))
    print(f"[INFO] Found {len(queued)} ai_results rows to process for history_id={history_id}")

    docs, hits, misses = [], 0, 0
    for q in queued:
        raw_id = q.get("raw_id")
        url    = q.get("url")
        raw_doc = _get_raw_doc_by_ref(db, raw_id, url)

        if not raw_doc:
            ai = db.ai_results.find_one({"_id": q["_id"]}, {"ai_summary":1, "ai_title":1})
            text_fallback = ((ai or {}).get("ai_title","") + "\n" + (ai or {}).get("ai_summary","")).strip()
            if text_fallback:
                hits += 1

                # fallback: look into ai_results for any stored engagement/meta
                ai_meta = db.ai_results.find_one(
                    {"_id": q.get("_id")},
                    {"engagement": 1, "stats": 1, "metrics": 1, "meta.engagement": 1}
                ) or {}

                eng = (
                    ai_meta.get("engagement")
                    or ai_meta.get("stats")
                    or ai_meta.get("metrics")
                    or (ai_meta.get("meta") or {}).get("engagement")
                    or {}
                )

                docs.append({
                    "_id": raw_id or url,
                    "text": text_fallback,
                    "engagement": eng,
                    "source": q.get("source"),
                    "published_ts": q.get("published_ts"),
                    "url": url,
                })

                continue
            misses += 1
            continue

        hits += 1
        docs.append({
            "_id": raw_id or url,
            "text": raw_doc.get("text",""),
            "engagement": raw_doc.get("engagement", {}),
            "source": q.get("source"),
            "published_ts": q.get("published_ts"),
            "url": url,
        })

    print(f"[INFO] Joined {hits} docs with text (misses: {misses})")
    return docs

def _first_sentences(text: str, max_chars: int = 280) -> str:
    sents = re.split(r'(?<=[.!?])\s+', (text or "").strip())
    out = []
    total = 0
    for s in sents:
        if not s: 
            continue
        if total + len(s) > max_chars and out:
            break
        out.append(s)
        total += len(s) + 1
    return (" ".join(out)).strip()[:max_chars]

def safe_summarize(text: str) -> str:
    try:
        summ = (generate_summary(text) or "").strip()
    except Exception:
        summ = ""
    if len(summ) < 40:
        summ = _first_sentences(text, 320)
    return summ

def safe_topic(text: str, fallback_tag: str = "Topic"):
    try:
        t = (detect_topic_simple(text) or "").strip()
    except Exception:
        t = ""
    return t if t else fallback_tag



# ---------------------------------------------------------------------------
# MAIN AI PIPELINE
# ---------------------------------------------------------------------------
def run(history_id: str, keyword: str):
    # Auto-seed queued rows if none exist
    from ai.ranking_algorithm.seed_ai_results import main as seed_once
    from ai.ranking_algorithm.check_history import clauses as _clauses

    hid_clause = _clauses(history_id)
    if db.ai_results.count_documents({**hid_clause, "status": "queued"}) == 0:
        seed_once(history_id)

    docs = fetch_docs(history_id)
    if not docs:
        print("[INFO] No articles waiting for AI processing.")
        return []
    print(f"[INFO] Processing {len(docs)} articles for keyword='{keyword}'")
    use_algos = ["tfidf", "bm25", "sbert", "engagement"]
    weights = DEFAULT_WEIGHTS

    # BM25 first-pass
    bm25 = BM25Scorer.from_docs(docs, k1=1.5, b=0.75)
    bm25_raw = bm25.score_all_for_query(keyword)
    bm25_scores = minmax_normalize(bm25_raw)
    top_ids = set(sorted(bm25_scores, key=bm25_scores.get, reverse=True)[:TOPK])

    print(bm25_scores)

    rows: List[Tuple[float, Dict[str, Any], Dict[str, float]]] = []
    for d in docs:
        per_algo: Dict[str, float] = {}

        # BM25 (already normalized 0..1)
        per_algo["bm25"] = float(bm25_scores.get(d["_id"], 0.0))
        
        # TF-IDF / SBERT / Engagement
        for a in ["tfidf", "sbert", "engagement"]:
            try:
                if a == "sbert":
                    raw_score = ALGORITHMS["sbert"](keyword, d) if d["_id"] in top_ids else 0.0
                    print(f"[DEBUG] SBERT score for doc {d['_id']}: {raw_score}")
                elif a == "tfidf":
                    raw_score = ALGORITHMS["tfidf"](keyword, d)
                    print(f"[DEBUG] TF-IDF score for doc {d['_id']}: {raw_score}")
                elif a == "engagement":
                    raw_score = ALGORITHMS["engagement"](keyword, d)
                    print(f"[DEBUG] Engagement score for doc {d['_id']}: {raw_score}")
                else:
                    raw_score = 0.0
            except Exception:
                raw_score = 0.0
            per_algo[a] = max(0.0, min(1.0, float(raw_score)))



        # Calculate weighted score before word count penalty
        final_score = sum(per_algo.get(name, 0.0) * weights.get(name, 0.0) for name in use_algos)

        # Apply word count penalty to reduce ranking of very short posts
        # Posts < 50 words get heavy penalty, 50-100 words gradual penalty, >100 words no penalty
        penalized_score = apply_word_count_penalty(
            final_score,
            d["text"],
            min_words=50,
            target_words=100,
            verbose=False  # Set to True for debugging
        )

        rows.append((penalized_score, d, per_algo))

    rows.sort(key=lambda x: x[0], reverse=True)

    # Summarize + Topic + Sentiment + Write back
    items = []
    for rank, (score, d, per_algo) in enumerate(rows, start=1):
        # Generate new summary/topic
        summary = generate_summary(d["text"]) or ""
        topic   = detect_topic_simple(d["text"]) or ""

        # Generate tags using advanced topic detection
        try:
            topic_result = detect_topics(d["text"], strategy='nlp', use_topic_modeling=True)
            tags = topic_result.get("main_topics", [])[:5]  # Limit to top 5 tags
            # Capitalize tags properly
            tags = [tag.title() if tag else "" for tag in tags]
            tags = [tag for tag in tags if tag]  # Remove empty strings
            if not tags:
                tags = [topic] if topic else ["General"]
        except Exception as e:
            print(f"[WARN] Advanced topic detection failed: {e}, falling back to simple")
            tags = [topic] if topic else ["General"]

        # Preserve existing ai_title / ai_summary if blank
        hid_q = clauses(history_id)
        existing = db.ai_results.find_one(
            {"$and": [{"url": d["url"]}, hid_q]},
            {"ai_title": 1, "ai_summary": 1}
        )
        if existing:
            if not topic and existing.get("ai_title"):
                topic = existing["ai_title"]
            if not summary and existing.get("ai_summary"):
                summary = existing["ai_summary"]

        # Fallbacks if both still empty
        if not summary:
            summary = (d["text"][:400] + "…") if len(d["text"]) > 400 else d["text"]
        if not topic:
            topic = "General"

        sentiment = quick_sentiment(d["text"], method='vader')

        # Count words for metadata
        from ai.ranking_algorithm.word_count_penalty import count_words
        word_count = count_words(d["text"])

        # Get raw engagement data (not the score, but the actual metrics)
        engagement_data = d.get("engagement") or {}

        items.append({
            "url": d["url"],
            "raw_id": d["_id"],
            "rank": rank,
            "relevance_score": score,
            "per_algo_scores": per_algo,
            "engagement_score": per_algo.get("engagement", 0.0),  # Extract engagement score for easy access
            "engagement_metrics": engagement_data,  # Store actual engagement data (likes, comments, etc.)
            "word_count": word_count,  # Track word count for analysis
            "ai_title": topic,
            "ai_summary": summary,
            "tags": tags,  # Now uses proper topic list from advanced detection
            "sentiment": sentiment,
            "source": d["source"],
            "published_ts": d["published_ts"],
            "status": "done",
        })
    write_ai_results_batch(history_id, items)
    print(f"[SUCCESS] Processed & saved {len(items)} AI-ranked articles.")
    return rows
    

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    history_id = "68fdda1caf9de874acb5a32a"  # Example history ID
    keyword = "artificial intelligence"
    run(history_id, keyword)
