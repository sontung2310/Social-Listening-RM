from typing import Any, Iterable, Tuple, List, Dict, Optional
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from pymongo import MongoClient, UpdateOne
from pymongo.server_api import ServerApi
import certifi

from config import ARTICLE_MONGODB_URI, ARTICLE_MONGODB_DBNAME

_mongo_client = None
_mongo_db = None

def get_mongo_db() -> Any:
    """Return the cached article/AI MongoDB database handle."""
    global _mongo_client, _mongo_db
    if _mongo_db is not None:
        return _mongo_db
    if not ARTICLE_MONGODB_URI or not ARTICLE_MONGODB_DBNAME:
        raise RuntimeError(
            "Article Mongo settings missing: ARTICLE_MONGODB_URI / ARTICLE_MONGODB_DBNAME"
        )
    _mongo_client = MongoClient(
        ARTICLE_MONGODB_URI,
        server_api=ServerApi("1"),
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
    )
    _mongo_db = _mongo_client[ARTICLE_MONGODB_DBNAME]
    return _mongo_db

# HISTORY helpers 
def create_history(
    subject: str,
    location: str,
    industry: str,
    sources_used: List[str],
    params: Dict,
    ai_target: int = 100,
    ttl_days: Optional[int] = None,
) -> ObjectId:
    """
    Inserts a new history document and returns its _id.
    """
    db = get_mongo_db()
    now = datetime.now(timezone.utc)
    doc = {
        "subject": subject,
        "location": location,
        "industry": industry,
        "sources_used": sources_used,
        "params": params or {},
        "created_at": now,
        # AI status
        "ai_ready": False,
        "ai_count": 0,
        "ai_target": ai_target,
        "started_at": None,
        "last_updated": None,
        "finished_at": None,
    }
    if ttl_days:
        doc["expires_at"] = now + timedelta(days=ttl_days)

    res = db["history"].insert_one(doc)
    return res.inserted_id


def mark_history_ai_started(history_id: ObjectId):
    db = get_mongo_db()
    now = datetime.now(timezone.utc)
    db["history"].update_one(
        {"_id": ObjectId(history_id)},
        {"$set": {"started_at": now, "last_updated": now}}
    )


def mark_history_ai_progress(history_id: ObjectId, ai_count: int):
    db = get_mongo_db()
    now = datetime.now(timezone.utc)
    db["history"].update_one(
        {"_id": ObjectId(history_id)},
        {"$set": {"ai_count": ai_count, "last_updated": now}}
    )


def mark_history_ai_done(history_id: ObjectId, total_count: Optional[int] = None):
    db = get_mongo_db()
    now = datetime.now(timezone.utc)
    updates = {"ai_ready": True, "finished_at": now, "last_updated": now}
    if total_count is not None:
        updates["ai_count"] = total_count
    db["history"].update_one({"_id": ObjectId(history_id)}, {"$set": updates})

# RAW INSIGHTS

def persist_raw_insights(rows: Iterable[dict]) -> Tuple[int, int]:
    """
    Upsert rows into 'raw_insights' by unique 'url'.
    Returns (created_count, updated_count).
    """
    db = get_mongo_db()
    col = db["raw_insights"]

    created = 0
    updated = 0
    now = datetime.now(timezone.utc)

    for p in rows:
        url = (p.get("url") or "").strip()
        if not url:
            continue

        res = col.update_one(
            {"url": url},
            {
                "$set": {
                    "url": url,
                    "source": (p.get("source") or "").strip(),
                    "title": p.get("title") or "",
                    "text": p.get("text") or "",
                    "text_html": p.get("text_html") or "",
                    "author": p.get("author") or None,
                    "published_ts": p.get("published_ts"),
                    "crawled_at": p.get("crawled_at"),
                    "engagement": p.get("engagement") or None,
                    "tags": p.get("tags") if "tags" in p else None,
                    "influencer_mentions": p.get("influencer_mentions") if "influencer_mentions" in p else None,
                    "backlinks": p.get("backlinks") if "backlinks" in p else None,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True
        )

        if res.upserted_id is not None:
            created += 1
        elif res.matched_count:
            updated += 1

    return created, updated


# AI RESULTS (queue + output)

def _extract_simple_tags(text: str, max_tags: int = 5) -> list:
    """
    Extract simple tags from text using basic keyword extraction.
    This provides immediate tags before full AI processing.
    """
    import re
    from collections import Counter

    if not text:
        return []

    # Common stop words to exclude
    stop_words = {
        'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i', 'it', 'for',
        'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at', 'this', 'but', 'his',
        'by', 'from', 'they', 'we', 'say', 'her', 'she', 'or', 'an', 'will', 'my',
        'one', 'all', 'would', 'there', 'their', 'what', 'so', 'up', 'out', 'if',
        'about', 'who', 'get', 'which', 'go', 'me', 'when', 'make', 'can', 'like',
        'just', 'him', 'know', 'take', 'into', 'year', 'your', 'some', 'could',
        'them', 'see', 'other', 'than', 'then', 'now', 'look', 'only', 'come',
        'its', 'over', 'also', 'back', 'after', 'use', 'two', 'how', 'our',
        'work', 'first', 'well', 'way', 'even', 'new', 'want', 'because', 'any',
        'these', 'give', 'most', 'us', 'is', 'are', 'was', 'been', 'has', 'had'
    }

    words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())

    filtered = [w for w in words if w not in stop_words]

    if not filtered:
        return []

    word_counts = Counter(filtered)
    top_words = [word for word, count in word_counts.most_common(max_tags)]

    tags = [word.title() for word in top_words]

    return tags[:max_tags]


def seed_ai_result_stubs(history_id: ObjectId, rows: Iterable[dict]) -> int:
    """
    Create 'queued' ai_results stubs for this run, one per URL.
    NOW INCLUDES: Immediate basic tag generation for trending topics.
    Idempotent upserts keyed by (history_id, url).
    Returns number of upserts attempted.
    """
    db = get_mongo_db()
    now = datetime.now(timezone.utc)

    urls = [(p.get("url") or "").strip() for p in rows if p.get("url")]
    urls = [u for u in urls if u]
    if not urls:
        return 0

    raw_map = {
        r["url"]: r["_id"]
        for r in db["raw_insights"].find({"url": {"$in": urls}}, {"_id": 1, "url": 1})
    }

    ops = []
    tags_debug = []  
    for p in rows:
        url = (p.get("url") or "").strip()
        if not url:
            continue

        title = p.get("title") or ""
        text = p.get("text") or ""
        combined_text = f"{title} {text}"
        tags = _extract_simple_tags(combined_text, max_tags=5)

        if len(tags_debug) < 3:
            tags_debug.append({
                "url": url[:50],
                "has_title": bool(title),
                "has_text": bool(text),
                "text_length": len(combined_text),
                "tags": tags,
                "source": p.get("source")
            })

        if not tags:
            source = (p.get("source") or "").strip()
            if source:
                tags = [source.replace("_", " ").title()]
            else:
                tags = ["General"]  

        selector = {"history_id": ObjectId(history_id), "url": url}

        set_on_insert = {
            "history_id": ObjectId(history_id),
            "url": url,
            "raw_id": raw_map.get(url),
            "source": (p.get("source") or "").strip(),
            "published_ts": p.get("published_ts"),
            "status": "queued",
            "created_at": now,
        }

        set_fields = {
            "tags": tags,  
        }

        ops.append(UpdateOne(
            selector,
            {
                "$setOnInsert": set_on_insert,
                "$set": set_fields 
            },
            upsert=True
        ))

    if ops:
        result = db["ai_results"].bulk_write(ops)
        print(f"[INFO] Seeded {len(ops)} ai_results with immediate tags")
        if tags_debug:
            print(f"[DEBUG] Sample tag generation:")
            for sample in tags_debug:
                print(f"  - URL: {sample['url']}")
                print(f"    Has title: {sample['has_title']}, Has text: {sample['has_text']}, Text len: {sample['text_length']}")
                print(f"    Tags: {sample['tags']}, Source: {sample['source']}")
    return len(ops)

def write_ai_results_batch(history_id: ObjectId, items: List[Dict]) -> Tuple[int, int]:
    """
    Upsert a batch of ai_results for a given history_id.
    Each item should include at least: url, rank, ai_title, ai_summary.
    Optionally may include: sentiment, engagement metrics (likes, shares, comments, etc.)
    """
    db = get_mongo_db()
    col = db["ai_results"]

    ops = []
    now = datetime.now(timezone.utc)
    for it in items:
        url = (it.get("url") or "").strip()
        if not url:
            continue

        selector = {"history_id": ObjectId(history_id), "url": url}
        docset = {
            "history_id": ObjectId(history_id),
            "url": url,
            "raw_id": it.get("raw_id"),
            "rank": it.get("rank"),
            "relevance_score": it.get("relevance_score"),
            "ai_title": it.get("ai_title"),
            "ai_summary": it.get("ai_summary"),
            "tags": it.get("tags"),
            "influencer_mentions": it.get("influencer_mentions"),
            "backlinks": it.get("backlinks"),
            "source": it.get("source"),
            "published_ts": it.get("published_ts"),
            "status": it.get("status") or "done",
            "finished_at": now,
            "sentiment": it.get("sentiment"),
            "engagement_metrics": it.get("engagement_metrics"),  
        }

        ops.append(
            UpdateOne(
                selector,
                {"$set": docset, "$setOnInsert": {"created_at": now}},
                upsert=True
            )
        )

    result = col.bulk_write(ops) if ops else None
    upserts = getattr(result, "upserted_count", 0) if result else 0
    updates = getattr(result, "modified_count", 0) if result else 0
    return upserts, updates


def persist_posts(rows: Iterable[dict]) -> Tuple[int, int]:
    """
    Backward-compatible shim that writes into 'raw_insights'.
    """
    return persist_raw_insights(rows)

# Company profile helpers

def _iso_z(dt: datetime) -> str:
    """Convert a datetime to ISO string with Z suffix (UTC)."""
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_card_block(now: datetime) -> dict:
    """Return default structure for each company card."""
    return {
        "data": [],
        "updated_at": None,
        "next_refresh_at": _iso_z(now + timedelta(days=7)),
    }

def upsert_company_profile(profile: dict):
    """
    Insert or update a company profile by name with card placeholders.
    Expected keys: { name: str, description: str, competitors?: list[str] }
    """
    db = get_mongo_db()
    now = datetime.now(timezone.utc)

    name = (profile.get("name") or "").strip()
    desc = (profile.get("description") or "").strip()
    comps = profile.get("competitors", [])
    if not name:
        raise ValueError("company profile name is required")

    if comps is None:
        comps = []
    if not isinstance(comps, list):
        raise ValueError("competitors must be a list of strings")
    comps = sorted({str(c).strip() for c in comps if str(c).strip()})

    # Default cards for each section
    cards = {
        "trending": _default_card_block(now),
        "newsfeed": _default_card_block(now),
        "ideas": _default_card_block(now),
        "backlinks": _default_card_block(now),
        "opportunities": _default_card_block(now),
        "new_competitors": _default_card_block(now), 
    }

    db["company_profiles"].update_one(
        {"name": name},
        {
            "$set": {
                "name": name,
                "description": desc,
                "competitors": comps,
            },
            "$setOnInsert": {
                "created_at": now,
                "cards": cards, 
            },
        },
        upsert=True
    )

    db["company_profiles"].update_one(
        {"name": name, "cards.new_competitors": {"$exists": False}},
        {"$set": {"cards.new_competitors": _default_card_block(now)}}
    )

def get_company_profile(name: Optional[str] = None) -> Optional[dict]:
    """
    Return one company profile.
    - If `name` is provided, return that specific profile.
    - Else, return the most recently created one.
    """
    db = get_mongo_db()
    if name:
        return db["company_profiles"].find_one({"name": name})
    return db["company_profiles"].find_one(sort=[("created_at", -1)])
