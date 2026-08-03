import logging, time, json, re
from datetime import datetime, date, timezone, timedelta
from typing import Any

from flask import Blueprint, jsonify, request, make_response

from bson import ObjectId

from .analytics import (
    trend_timeseries_by_day,
    trend_top_tags,
    trend_by_source,
    _parse_iso_to_date,
    _coerce_topics_list,  
    global_top_topics,
    _as_list
)

from db.persist import (
    get_mongo_db,
    get_company_profile,
    _iso_z,
)

from config import NEWSAPI_KEY as NEWSAPI_DEFAULT_KEY
from config import SERPAPI_KEY as SERPAPI_DEFAULT_KEY

logger = logging.getLogger(__name__)
api_bp = Blueprint("api", __name__)

# utils 
def _json_safe(obj: Any):
    """Recursively convert BSON/unsupported types to JSON-serializable ones."""
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        if isinstance(obj, datetime) and obj.tzinfo is not None:
            return obj.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]
    return obj

def _j(payload: Any, status_code: int = 200):
    """jsonify + status in one go (safe for Mongo ObjectIds / datetimes)."""
    resp = make_response(jsonify(_json_safe(payload)), status_code)
    return resp

# NewsAPI plumbing
NEWSAPI_ENDPOINT = "https://newsapi.org/v2/everything"

def _map_newsapi_articles(articles):
    mapped = []
    for a in (articles or []):
        source_name = None
        src = a.get("source")
        if isinstance(src, dict):
            source_name = src.get("name")
        if not source_name:
            source_name = src if isinstance(src, str) else "Unknown"
        mapped.append({
            "title": a.get("title") or "",
            "description": a.get("description") or "",
            "url": a.get("url") or "",
            "author": a.get("author") or None,
            "source": source_name,
            "publishedAt": a.get("publishedAt"),
        })
    return mapped

import requests
def _fetch_from_newsapi(query: str, api_key: str, page_size: int = 50):
    params = {
        "q": query,
        "pageSize": max(10, min(int(page_size), 100)),
        "language": "en",
        "sortBy": "publishedAt",
        "apiKey": api_key,
    }
    r = requests.get(NEWSAPI_ENDPOINT, params=params, timeout=25)
    r.raise_for_status()
    payload = r.json()
    return _map_newsapi_articles(payload.get("articles") or [])

# SerpAPI (Google Trends)
SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
URL_RE = re.compile(r'https?://', re.I)

def _sanitize_topics(seq: list[str], *, max_len: int = 60) -> list[str]:
    out, seen = [], set()
    for s in (seq or []):
        if not isinstance(s, str):
            continue
        s = " ".join(s.strip().split())
        if not s:
            continue
        if URL_RE.search(s):
            continue
        if len(s) < 2 or len(s) > max_len:
            continue
        if not re.search(r"[A-Za-z]", s):
            continue
        if " " not in s and len(s) >= 16 and re.match(r"^[A-Za-z0-9_\-]+$", s):
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out

def _serpapi_date_for_days(days: int) -> str:
    try:
        d = int(days)
    except Exception:
        d = 30
    if d <= 7:   return "now 7-d"
    if d <= 30:  return "today 1-m"
    if d <= 90:  return "today 3-m"
    return "today 12-m"

def _coerce_topic_strings(obj, acc: set):
    if obj is None:
        return
    if isinstance(obj, str):
        s = " ".join(obj.strip().split())
        if s and not URL_RE.search(s) and re.search(r"[A-Za-z]", s):
            acc.add(s)
        return
    if isinstance(obj, list):
        for it in obj:
            _coerce_topic_strings(it, acc)
        return
    if isinstance(obj, dict):
        for k in ("topic", "topic_title", "title", "query", "name", "keyword"):
            v = obj.get(k)
            if isinstance(v, str):
                s = " ".join(v.strip().split())
                if s and not URL_RE.search(s) and re.search(r"[A-Za-z]", s):
                    acc.add(s)
        for v in obj.values():
            _coerce_topic_strings(v, acc)

def _fetch_trending_topics_serpapi(query: str | None, *, geo: str = "AU", days: int = 30, limit: int = 30, api_key: str = SERPAPI_DEFAULT_KEY) -> list[str]:
    topics: set[str] = set()
    if (query or "").strip():
        params = {
            "engine": "google_trends",
            "q": query.strip(),
            "data_type": "RELATED_TOPICS",
            "date": _serpapi_date_for_days(days),
            "geo": geo or "AU",
            "api_key": api_key,
        }
        try:
            r = requests.get(SERPAPI_ENDPOINT, params=params, timeout=25)
            r.raise_for_status()
            payload = r.json() or {}
            _coerce_topic_strings(payload.get("related_topics"), topics)
            _coerce_topic_strings(payload.get("related_queries"), topics)
        except Exception:
            pass

    if not topics:
        params = {
            "engine": "google_trends_trending_now",
            "geo": geo or "AU",
            "api_key": api_key,
        }
        try:
            r = requests.get(SERPAPI_ENDPOINT, params=params, timeout=25)
            r.raise_for_status()
            payload = r.json() or {}
            _coerce_topic_strings(payload.get("trending_searches"), topics)
        except Exception:
            pass
    return [t for t in topics if t][:limit]

# Lazy AI runners — avoid importing heavy ai.* modules at Flask startup
_ai_runners = {}

def _ai_runner(name: str):
    """Import and cache an AI collection_card runner on first use."""
    if name in _ai_runners:
        return _ai_runners[name]
    runner = None
    try:
        if name == "trending":
            from ai.collection_card.trending_topics.main_relevancy import run as runner
        elif name == "ideas":
            from ai.collection_card.ideas.main_ideas import run as runner
        elif name == "competitors":
            from ai.collection_card.new_competitors.main_new_competitors import run as runner
        elif name == "engaged_links":
            from ai.collection_card.engaged_links.main_engaged import run as runner
        elif name == "opportunities":
            from ai.collection_card.opportunities.main_opportunities import run as runner
        elif name == "newsfeed":
            from ai.collection_card.news_feed.main_news import run as runner
    except Exception as e:
        logger.warning("Failed to import ai runner %s: %s", name, e)
        runner = None
    _ai_runners[name] = runner
    return runner


@api_bp.route("/health/", methods=["GET"])
def health():
    return _j({"status": "ok", "version": "v1"}, 200)

@api_bp.route("/search/", methods=["POST"])
def search_posts():
    """In-process crawl/search ingest was removed from Pace-Unit.

    Crawl lives in Data-Crawler-Task. A Crawl Management API (SQS command queue)
    is pending — see code/FUTURE_WORK.md.
    """
    return _j(
        {
            "error": "not_implemented",
            "message": (
                "Crawl/search ingest moved to Data-Crawler-Task; "
                "Crawl Management API pending — see code/FUTURE_WORK.md"
            ),
        },
        501,
    )

@api_bp.route("/history/", methods=["GET"])
def list_history():
    try:
        db = get_mongo_db()
        limit = int(request.args.get("limit", 20))
        limit = max(1, min(limit, 100))
        ai_ready_param = request.args.get("ai_ready")
        filt = {}
        if ai_ready_param:
            filt["ai_ready"] = ai_ready_param.lower() == "true"

        docs = list(db["history"].find(filt).sort("created_at", -1).limit(limit))
        out = []
        for d in docs:
            out.append({
                "history_id": str(d["_id"]),
                "subject": d.get("subject"),
                "location": d.get("location"),
                "industry": d.get("industry"),
                "sources_used": d.get("sources_used", []),
                "created_at": d.get("created_at"),
                "ai_ready": d.get("ai_ready", False),
                "ai_count": d.get("ai_count", 0),
                "ai_target": d.get("ai_target", 100),
            })
        return _j(out, 200)
    except Exception as e:
        logger.exception("list_history error: %s", e)
        return _j({"error": str(e)}, 500)

@api_bp.route("/search/status/", methods=["GET"])
def get_search_status():
    hid = request.args.get("history_id")
    if not hid:
        return _j({"error": "history_id is required"}, 400)
    try:
        db = get_mongo_db()
        doc = db["history"].find_one({"_id": ObjectId(hid)})
        if not doc:
            return _j({"error": "not found"}, 404)
        return _j({
            "history_id": str(doc["_id"]),
            "subject": doc.get("subject"),
            "ai_ready": doc.get("ai_ready", False),
            "ai_count": doc.get("ai_count", 0),
            "ai_target": doc.get("ai_target", 100),
            "created_at": doc.get("created_at"),
            "finished_at": doc.get("finished_at"),
        }, 200)
    except Exception as e:
        logger.exception("get_search_status error: %s", e)
        return _j({"error": str(e)}, 500)

@api_bp.route("/trends/", methods=["GET"])
def get_trends():
    """
    GET /api/trends/?history_id=<id>&days=30
    Returns a simple list of top tags (not the whole object).
    """
    hid = request.args.get("history_id")
    if not hid:
        return _j({"error": "history_id is required"}, 400)

    try:
        days = int(request.args.get("days", 30))
    except Exception:
        days = 30

    try:
        oid = ObjectId(hid)
        tags = trend_top_tags(oid, days, top_k=20)
        tag_list = [t["_id"] for t in tags if "_id" in t]
        return _j(tag_list, 200)
    except Exception as e:
        logger.exception("get_trends error: %s", e)
        return _j({"error": str(e)}, 500)



@api_bp.route("/results/", methods=["GET"])
def get_results():
    hid = (request.args.get("history_id") or "").strip()
    if not hid:
        return _j({"error": "history_id is required"}, 400)

    status_filter = (request.args.get("status") or "done").strip().lower()
    sort_key = (request.args.get("sort") or "rank").strip()
    order = (request.args.get("order") or "asc").strip().lower()
    order_val = 1 if order in ("asc", "ascending") else -1
    if sort_key not in {"rank", "published_ts", "relevance_score"}:
        sort_key = "rank"

    try:
        db = get_mongo_db()
        q = {"history_id": ObjectId(hid)}
        if status_filter:
            q["status"] = status_filter
        cursor = db["ai_results"].find(q).sort(sort_key, order_val)
        docs = list(cursor)

        results = []
        for d in docs:
            engagement = d.get("engagement_metrics") or d.get("engagement")
            results.append({
                "rank": d.get("rank"),
                "url": d.get("url"),
                "ai_title": d.get("ai_title"),
                "ai_summary": d.get("ai_summary"),
                "tags": d.get("tags"),
                "relevance_score": d.get("relevance_score"),
                "published_ts": d.get("published_ts"),
                "source": d.get("source"),
                "status": d.get("status"),
                "sentiment": d.get("sentiment"),
                "engagement_metrics": engagement,
                "engagement": engagement,
            })
        return _j({"history_id": hid, "total": len(results), "results": results}, 200)
    except Exception as e:
        logger.exception("get_results (no-pagination) error: %s", e)
        return _j({"error": str(e)}, 500)

@api_bp.route("/cards/trending/", methods=["GET"])
def card_trends():
    db = get_mongo_db()
    company_id   = (request.args.get("company_id") or "").strip() or None
    company_name = (request.args.get("company") or "").strip() or None
    force        = str(request.args.get("force", "0")).strip().lower() in ("1", "true", "yes", "y", "on")
    use_serpapi  = str(request.args.get("use_serpapi", "1")).strip().lower() in ("1", "true", "yes", "y", "on")
    geo          = (request.args.get("geo") or "AU").strip().upper()
    override_q   = (request.args.get("query") or "").strip() or None

    try:
        threshold = float(request.args.get("threshold", 0.5))
    except Exception:
        threshold = 0.5
    try:
        limit = int(request.args.get("limit", 10))
    except Exception:
        limit = 10
    limit = max(1, min(limit, 50))

    full = (request.args.get("full", "0").strip().lower() in ("1", "true"))
    try:
        days = int(request.args.get("days", 30))
    except Exception:
        days = 30

    if not company_id and company_name:
        doc = get_company_profile(name=company_name)
        if not doc:
            return _j({"error": f"Company '{company_name}' not found"}, 404)
        company_id = str(doc["_id"])
    if not company_id:
        return _j({"error": "company_id (or company name) is required"}, 400)

    def _read_from_db_and_respond():
        fresh = db["company_profiles"].find_one(
            {"_id": ObjectId(company_id)}, {"cards.trending": 1}
        ) or {}
        trending = ((fresh.get("cards") or {}).get("trending") or {})
        data = trending.get("data") or []
        if full:
            if data and isinstance(data[0], str):
                return _j([{"topic": t, "relevance": None} for t in data][:limit], 200)
            return _j((data or [])[:limit], 200)
        else:
            if data and isinstance(data[0], dict):
                topics = [x.get("topic") for x in data if isinstance(x, dict) and x.get("topic")]
                return _j(topics[:limit], 200)
            return _j((data or [])[:limit], 200)

    prof = db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"cards": 1}) or {}
    cards = prof.get("cards") or {}
    trending = cards.get("trending") or {}
    next_refresh_at   = trending.get("next_refresh_at")
    next_refresh_date = _parse_iso_to_date(next_refresh_at)
    today_utc         = datetime.now(timezone.utc).date()

    if not force and next_refresh_date and today_utc < next_refresh_date and (trending.get("data") or []):
        return _read_from_db_and_respond()

    raw_topics: list[str] = []
    if use_serpapi:
        q_for_trends = override_q or company_name or None
        try:
            pool = max(30, limit)
            raw_topics = _fetch_trending_topics_serpapi(
                q_for_trends,
                geo=geo or "AU",
                days=max(days, 30),
                limit=pool,
                api_key=SERPAPI_DEFAULT_KEY,
            )
        except Exception as e:
            logger.warning("SerpAPI fetch failed; falling back. %s", e)

    if not raw_topics:
        try:
            raw_topics = global_top_topics(days=max(days, 30), limit=max(30, limit))
        except Exception as e:
            logger.exception("global_top_topics failed: %s", e)
            return _j(_read_from_db_and_respond().get_json(), 200)

    raw_topics = _sanitize_topics(raw_topics, max_len=60)
    if not raw_topics:
        return _read_from_db_and_respond()

    runner_ok = True
    trending_run = _ai_runner("trending")
    if trending_run is not None:
        try:
            trending_run(company_id=company_id, trending_topics=raw_topics)
        except Exception as e:
            runner_ok = False
            logger.warning("trending_run failed; fallback-persist. %s", e)
    else:
        runner_ok = False

    fresh = db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"cards": 1}) or {}
    cards = fresh.get("cards") or {}

    if "trending_topics" in cards and (not cards.get("trending") or not (cards["trending"].get("data") or [])):
        src = cards["trending_topics"] or {}
        block = {
            "data": src.get("data") or [],
            "updated_at": src.get("updated_at") or _iso_z(datetime.now(timezone.utc)),
            "next_refresh_at": src.get("next_refresh_at") or None,
        }
        db["company_profiles"].update_one(
            {"_id": ObjectId(company_id)},
            {"$set": {"cards.trending": block}}
        )
        fresh = db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"cards.trending": 1}) or {}

    cur = ((fresh.get("cards") or {}).get("trending") or {})
    if (not runner_ok) and (force or not (cur.get("data") or [])):
        now = datetime.now(timezone.utc)
        block = {
            "data": raw_topics[:limit],
            "updated_at": _iso_z(now),
            "next_refresh_at": _iso_z(now + timedelta(days=7)),
        }
        db["company_profiles"].update_one(
            {"_id": ObjectId(company_id)},
            {"$set": {"cards.trending": block}}
        )
        cur = block

    if not cur.get("next_refresh_at"):
        now = datetime.now(timezone.utc)
        db["company_profiles"].update_one(
            {"_id": ObjectId(company_id)},
            {"$set": {"cards.trending.next_refresh_at": _iso_z(now + timedelta(days=7))}}
        )
    return _read_from_db_and_respond()

@api_bp.route("/cards/newsfeed/", methods=["GET"])
def news_feed():
    db = get_mongo_db()
    company_id   = (request.args.get("company_id") or "").strip() or None
    company_name = (request.args.get("company") or "").strip() or None
    force        = str(request.args.get("force", "0")).strip().lower() in ("1", "true", "yes", "y", "on")

    try:
        limit = int(request.args.get("limit", 10))
    except Exception:
        limit = 10
    limit = max(1, min(limit, 100))

    try:
        max_age_days = int(request.args.get("max_age_days", 7))
    except Exception:
        max_age_days = 7

    sources_param = (request.args.get("sources") or "").strip()
    if sources_param:
        allowed_sources = {s.strip() for s in sources_param.split(",") if s.strip()}
    else:
        allowed_sources = {
            "news_rss", "bbc_rss", "techcrunch_rss", "guardian_api", "google_news_rss",
            "abc_au_rss", "cnn_rss", "reuters_rss"
        }

    use_newsapi = str(request.args.get("use_newsapi", "0")).strip().lower() in ("1", "true", "yes", "y", "on")
    query       = (request.args.get("query") or "").strip()
    try:
        page_size = int(request.args.get("page_size", 50))
    except Exception:
        page_size = 50

    if not company_id and company_name:
        doc = get_company_profile(name=company_name)
        if not doc:
            return _j({"error": f"Company '{company_name}' not found"}, 404)
        company_id = str(doc["_id"])
    if company_id and not company_name:
        prof = db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"name": 1})
        if prof:
            company_name = prof.get("name")
    if not company_id:
        doc = get_company_profile(name=None)
        if not doc:
            return _j({"error": "company_id (or company name) is required"}, 400)
        company_id = str(doc["_id"])
        company_name = company_name or doc.get("name")

    def _read_from_db_and_respond():
        fresh = db["company_profiles"].find_one(
            {"_id": ObjectId(company_id)}, {"name": 1, "cards.newsfeed": 1}
        ) or {}
        name  = fresh.get("name") or company_name
        card  = ((fresh.get("cards") or {}).get("newsfeed") or {})
        data  = (card.get("data") or [])[:limit]
        return _j({"company": name, "company_id": company_id, "count": len(data), "items": data}, 200)

    prof  = db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"cards": 1}) or {}
    cards = prof.get("cards") or {}
    nf    = cards.get("newsfeed") or {}
    next_refresh_at   = nf.get("next_refresh_at")
    next_refresh_date = _parse_iso_to_date(next_refresh_at)
    today_utc         = datetime.now(timezone.utc).date()

    if not force and next_refresh_date and today_utc < next_refresh_date and (nf.get("data") or []):
        return _read_from_db_and_respond()

    now_ts   = int(time.time())
    cutoff   = now_ts - max_age_days * 86400
    pool_cap = 100
    pool_min = 50

    def _ts_to_iso_z(ts: int | None):
        if not ts:
            return None
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            return None

    cursor = (
        db["raw_insights"]
        .find(
            {"published_ts": {"$gte": cutoff}, "source": {"$in": list(allowed_sources)}},
            {"title": 1, "url": 1, "source": 1, "published_ts": 1, "text": 1, "author": 1, "summary": 1}
        )
        .sort("published_ts", -1)
        .limit(pool_cap)
    )

    raw_articles = []
    for r in cursor:
        title = (r.get("title") or "").strip()
        url   = (r.get("url") or "").strip()
        if not title or not url:
            continue
        raw_articles.append({
            "title": title,
            "description": (r.get("summary") or r.get("text") or "").strip(),
            "url": url,
            "author": (r.get("author") or None),
            "source": r.get("source"),
            "publishedAt": _ts_to_iso_z(r.get("published_ts")),
        })

    if use_newsapi:
        q = query or company_name or ""
        try:
            extra = _fetch_from_newsapi(q, api_key=NEWSAPI_DEFAULT_KEY, page_size=page_size)
        except Exception as e:
            logger.warning("NewsAPI fetch failed: %s", e)
            extra = []

        seen = {a["url"] for a in raw_articles if a.get("url")}
        for a in (extra or []):
            u = (a.get("url") or "").strip()
            if u and u not in seen:
                raw_articles.append(a)
                seen.add(u)

    raw_articles = raw_articles[:max(pool_min, limit)]

    if not raw_articles:
        now = datetime.now(timezone.utc)
        db["company_profiles"].update_one(
            {"_id": ObjectId(company_id)},
            {"$set": {"cards.newsfeed.next_refresh_at": _iso_z(now + timedelta(days=1))}},
            upsert=True,
        )
        return _j({"company": company_name, "company_id": company_id, "count": 0, "items": []}, 200)

    newsfeed_run = _ai_runner("newsfeed")
    if newsfeed_run is not None:
        try:
            newsfeed_run(company_id=company_id, news_articles=raw_articles)
        except Exception as e:
            logger.warning("newsfeed_run failed; continuing with schema migration/safety. %s", e)

    fresh = db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"cards": 1}) or {}
    cards = fresh.get("cards") or {}

    if "news_feed" in cards and (not cards.get("newsfeed") or not (cards["newsfeed"].get("data") or [])):
        src = cards["news_feed"] or {}
        block = {
            "data": src.get("data") or [],
            "updated_at": src.get("updated_at") or _iso_z(datetime.now(timezone.utc)),
            "next_refresh_at": src.get("next_refresh_at") or None,
        }
        db["company_profiles"].update_one(
            {"_id": ObjectId(company_id)},
            {"$set": {"cards.newsfeed": block}}
        )
    cur = ((fresh.get("cards") or {}).get("newsfeed") or {})
    if not cur.get("next_refresh_at"):
        now = datetime.now(timezone.utc)
        db["company_profiles"].update_one(
            {"_id": ObjectId(company_id)},
            {"$set": {"cards.newsfeed.next_refresh_at": _iso_z(now + timedelta(days=7))}}
        )
    return _j(db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"name":1, "cards.newsfeed":1}) or {}, 200)
    

@api_bp.route("/debug/mongo/", methods=["GET"])
def mongo_status():
    try:
        db = get_mongo_db()
        names = sorted(db.list_collection_names())
        counts = {}
        for c in ["raw_insights", "ai_results", "history"]:
            if c in names:
                counts[c] = db[c].count_documents({})
        return _j({"db": db.name, "collections": names, "counts": counts}, 200)
    except Exception as e:
        return _j({"error": str(e)}, 500)

@api_bp.route("/topics/top/", methods=["GET"])
def get_top_topics():
    try:
        days = int(request.args.get("days", 30))
    except Exception:
        days = 30
    try:
        limit = int(request.args.get("limit", 15))
    except Exception:
        limit = 15
    try:
        data = global_top_topics(days=days, limit=limit)
        return _j({"window_days": days, "topics": data}, 200)
    except Exception as e:
        logger.exception("get_top_topics error: %s", e)
        return _j({"error": str(e)}, 500)

@api_bp.route("/ai/ideas/", methods=["GET"])
def ai_generate_ideas():
    db = get_mongo_db()
    company_id   = (request.args.get("company_id") or "").strip() or None
    company_name = (request.args.get("company") or "").strip() or None
    force        = str(request.args.get("force", "0")).strip().lower() in ("1", "true", "yes", "y", "on")
    try:
        limit = int(request.args.get("limit", 10))
    except Exception:
        limit = 10
    limit = max(1, min(limit, 100))

    if not company_id and company_name:
        doc = get_company_profile(name=company_name)
        if not doc:
            return _j({"error": f"Company '{company_name}' not found"}, 404)
        company_id = str(doc["_id"])
    if not company_id:
        return _j({"error": "company_id (or company name) is required"}, 400)

    def _read_schema_and_respond():
        fresh = db["company_profiles"].find_one(
            {"_id": ObjectId(company_id)}, {"name": 1, "cards.ideas": 1}
        ) or {}
        name = fresh.get("name") or company_name
        ideas_card = ((fresh.get("cards") or {}).get("ideas") or {})
        data = ideas_card.get("data")
        if not data:
            data = ideas_card.get("ideas") or ideas_card.get("items") or []
            if data:
                db["company_profiles"].update_one(
                    {"_id": ObjectId(company_id)},
                    {"$set": {"cards.ideas.data": data}},
                )
                ideas_card["data"] = data
        data = (data or [])[:limit]
        return _j({"company": name, "company_id": company_id, "count": len(data), "insights": data}, 200)

    prof = db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"cards": 1})
    cards = (prof or {}).get("cards") or {}
    ideas_card = cards.get("ideas") or {}
    next_refresh_at = ideas_card.get("next_refresh_at")
    next_refresh_date = _parse_iso_to_date(next_refresh_at)
    today_utc = datetime.now(timezone.utc).date()
    if not force and next_refresh_date and today_utc < next_refresh_date and (ideas_card.get("data") or []):
        return _read_schema_and_respond()

    ideas_run = _ai_runner("ideas")
    if ideas_run is not None:
        try:
            ideas_run(company_id=company_id)
        except Exception as e:
            logger.warning("ideas_run failed; returning schema as-is. %s", e)
            return _read_schema_and_respond()

    fresh = db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"cards.ideas": 1}) or {}
    cur = ((fresh.get("cards") or {}).get("ideas") or {})
    if not cur.get("next_refresh_at"):
        now = datetime.now(timezone.utc)
        db["company_profiles"].update_one(
            {"_id": ObjectId(company_id)},
            {"$set": {"cards.ideas.next_refresh_at": _iso_z(now + timedelta(days=7))}}
        )
    return _read_schema_and_respond()

@api_bp.route("/ai/competitors/", methods=["GET", "POST"])
def ai_competitors():
    db = get_mongo_db()

    q = request.args
    body = (request.get_json(silent=True) or {}) if request.method == "POST" else {}

    company_id   = (q.get("company_id") or "").strip() or None
    company_name = (q.get("company")    or "").strip() or None
    force        = str(q.get("force", "0")).strip().lower() in ("1", "true", "yes", "y", "on")

    def _int(name, default):
        try:
            return int(q.get(name, default))
        except Exception:
            return default

    def _float(name, default):
        try:
            return float(q.get(name, default))
        except Exception:
            return default

    def _bool(name, default=False):
        v = q.get(name, None)
        if v is None:
            return default
        return str(v).strip().lower() in ("1", "true", "yes", "y", "on")

    limit_articles = _int("limit_articles", 80)
    min_relevance  = _float("min_relevance", 0.30)
    top_n          = _int("top_n", 10)
    min_score      = _float("min_score", 0.25)
    verbose        = _bool("verbose", False)

    if not company_id and not company_name and request.method == "POST":
        company_name = (body.get("company") or "").strip() or None

    if not company_id and company_name:
        doc = get_company_profile(name=company_name)
        if not doc:
            return _j({"error": f"Company '{company_name}' not found"}, 404)
        company_id = str(doc["_id"])

    if not company_id:
        return _j({"error": "company_id (or company name) is required"}, 400)

    try:
        _ = ObjectId(company_id)
    except Exception:
        return _j({"error": "invalid company_id (must be 24-character ObjectId)"}, 400)

    if company_id and not company_name:
        prof = db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"name": 1})
        if prof:
            company_name = prof.get("name")

    def _read_schema_and_respond():
        fresh = db["company_profiles"].find_one(
            {"_id": ObjectId(company_id)},
            {"name": 1, "cards.competitors": 1, "cards.new_competitors": 1}
        )
        if not fresh:
            return _j({"error": "company profile not found"}, 404)

        name  = fresh.get("name") or company_name
        cards = fresh.get("cards") or {}
        comp  = (cards.get("competitors") or {})

        data = comp.get("data") or comp.get("items")
        if not data:
            data = (cards.get("new_competitors") or {}).get("items") or []

        out = (data or [])[:top_n]
        return _j({"company": name, "company_id": company_id, "count": len(out), "competitors": out}, 200)

    prof = db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"cards": 1}) or {}
    cards = prof.get("cards") or {}
    comp  = cards.get("competitors") or {}
    next_refresh_at   = comp.get("next_refresh_at")
    next_refresh_date = _parse_iso_to_date(next_refresh_at)
    today_utc         = datetime.now(timezone.utc).date()

    if (not force) and next_refresh_date and today_utc < next_refresh_date and (comp.get("data") or comp.get("items")):
        return _read_schema_and_respond()

    try:
        competitors_run = _ai_runner("competitors")
        if competitors_run is not None:
            competitors_run(
                company_id=company_id,
                limit_docs=limit_articles,      
                min_relevance=min_relevance,
                days_back=180,                 
                top_n=top_n,
                persist=True,                   
                verbose=verbose,
            )
    except Exception as e:
        logger.warning("competitors_run failed; continuing with schema as-is. %s", e)

    fresh = db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"cards": 1}) or {}
    cards = fresh.get("cards") or {}
    newc  = cards.get("new_competitors") or {}
    items = newc.get("items") or []

    if items:
        now = datetime.now(timezone.utc)
        block = {
            "data": items[:top_n],
            "updated_at": _iso_z(now),
            "next_refresh_at": _iso_z(now + timedelta(days=7)),
        }
        db["company_profiles"].update_one(
            {"_id": ObjectId(company_id)},
            {"$set": {"cards.competitors": block}}
        )

    cur = db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"cards.competitors": 1}) or {}
    cur_block = ((cur.get("cards") or {}).get("competitors") or {})
    if not cur_block.get("next_refresh_at"):
        now = datetime.now(timezone.utc)
        db["company_profiles"].update_one(
            {"_id": ObjectId(company_id)},
            {"$set": {"cards.competitors.next_refresh_at": _iso_z(now + timedelta(days=7))}}
        )

    return _read_schema_and_respond()

@api_bp.route("/ai/backlinks/", methods=["GET"])
def ai_backlinks():
    engaged_links_run = _ai_runner("engaged_links")
    if engaged_links_run is None:
        return _j({"error": "engaged_links.run not available"}, 500)

    db = get_mongo_db()
    q = request.args

    company_id   = (q.get("company_id") or "").strip() or None
    company_name = (q.get("company")    or "").strip() or None
    force        = str(q.get("force", "0")).strip().lower() in ("1","true","yes","y","on")

    def _int(name, default):
        try: return int(q.get(name, default))
        except Exception: return default

    def _float(name, default):
        try: return float(q.get(name, default))
        except Exception: return default

    def _bool(name, default=False):
        v = q.get(name, None)
        if v is None: return default
        return str(v).strip().lower() in ("1","true","yes","y","on")

    top_n         = _int("limit", 20)        
    limit_docs    = _int("limit_docs", 400)
    min_relevance = _float("min_relevance", 0.10)
    days_back     = _int("days_back", 200)
    verbose       = _bool("verbose", False)

    if not company_id and company_name:
        doc = get_company_profile(name=company_name)
        if not doc:
            return _j({"error": f"Company '{company_name}' not found"}, 404)
        company_id = str(doc["_id"])

    if not company_id:
        return _j({"error": "company_id (or company name) is required"}, 400)

    try:
        _ = ObjectId(company_id)
    except Exception:
        return _j({"error": "invalid company_id (must be 24-character ObjectId)"}, 400)

    if company_id and not company_name:
        prof = db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"name": 1})
        if prof:
            company_name = prof.get("name")

    def _read_schema_and_respond():
        fresh = db["company_profiles"].find_one(
            {"_id": ObjectId(company_id)}, {"name": 1, "cards.engaged_links": 1}
        )
        if not fresh:
            return _j({"error": "company profile not found"}, 404)

        name = fresh.get("name") or company_name
        card = ((fresh.get("cards") or {}).get("engaged_links") or {})


        data = card.get("data") or card.get("items")

        if not data:
            urls = card.get("urls") or []
            if all(isinstance(u, str) for u in urls):
                data = urls
            else:
                data = [u.get("url") for u in urls if isinstance(u, dict) and u.get("url")]

        out = (data or [])[:top_n]
        return _j({
            "company": name,
            "company_id": company_id,
            "count": len(out),
            "engaged_links": out   
        }, 200)


    prof = db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"cards.engaged_links": 1}) or {}
    card = ((prof.get("cards") or {}).get("engaged_links") or {})
    next_refresh_at   = card.get("next_refresh_at")
    next_refresh_date = _parse_iso_to_date(next_refresh_at)
    today_utc         = datetime.now(timezone.utc).date()
    if (not force) and next_refresh_date and today_utc < next_refresh_date and (card.get("data") or card.get("items")):
        return _read_schema_and_respond()

    try:
        engaged_links_run(
            company_id=company_id,
            top_n=top_n,
            limit_docs=limit_docs,
            min_relevance=min_relevance,
            days_back=days_back,
            persist=True,
            verbose=verbose,
        )
    except Exception as e:
        logger.warning("engaged_links_run failed; continuing with schema as-is. %s", e)

    fresh = db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"cards.engaged_links": 1}) or {}
    card  = ((fresh.get("cards") or {}).get("engaged_links") or {})
    if card.get("items") and not card.get("data"):
        now = datetime.now(timezone.utc)
        migrate_block = {
            "data": card.get("items")[:top_n],
            "updated_at": card.get("updated_at") or _iso_z(now),
            "next_refresh_at": card.get("next_refresh_at") or _iso_z(now + timedelta(days=7)),
        }
        db["company_profiles"].update_one(
            {"_id": ObjectId(company_id)},
            {"$set": {"cards.engaged_links": migrate_block}}
        )

    cur = db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"cards.engaged_links": 1}) or {}
    cur_block = ((cur.get("cards") or {}).get("engaged_links") or {})
    if not cur_block.get("next_refresh_at"):
        now = datetime.now(timezone.utc)
        db["company_profiles"].update_one(
            {"_id": ObjectId(company_id)},
            {"$set": {"cards.engaged_links.next_refresh_at": _iso_z(now + timedelta(days=7))}}
        )

    return _read_schema_and_respond()


@api_bp.route("/ai/opportunities/", methods=["GET"])
def ai_opportunities():
    opportunities_run = _ai_runner("opportunities")
    if opportunities_run is None:
        return _j({"error": "opportunities.run not available"}, 500)
    db = get_mongo_db()
    company_id = (request.args.get("company_id") or "").strip()
    history_id = (request.args.get("history_id") or "").strip()
    if not company_id:
        return _j({"error": "company_id is required"}, 400)
    if not history_id:
        return _j({"error": "history_id is required"}, 400)
    try:
        limit = int(request.args.get("limit", 20))
    except Exception:
        limit = 20
    limit = max(1, min(limit, 200))
    try:
        _ = ObjectId(company_id); _ = ObjectId(history_id)
    except Exception:
        return _j({"error": "company_id and history_id must be valid ObjectId strings"}, 400)

    prof = db["company_profiles"].find_one({"_id": ObjectId(company_id)}, {"name": 1}) or {}
    company_name = prof.get("name")
    try:
        opportunities_run(company_id=company_id, history_id=history_id)
    except Exception as e:
        logger.exception("opportunities_run failed: %s", e)

    fresh = db["company_profiles"].find_one(
        {"_id": ObjectId(company_id)}, {"name": 1, "cards.opportunities": 1}
    ) or {}
    name = fresh.get("name") or company_name or None
    opp_card = ((fresh.get("cards") or {}).get("opportunities") or {})
    if isinstance(opp_card, list):
        items = opp_card; updated_at = None; next_refresh_at = None
    elif isinstance(opp_card, dict):
        items = (
            opp_card.get("data")
            or opp_card.get("opportunities")
            or opp_card.get("items")
            or opp_card.get("list")
            or []
        )
        updated_at = opp_card.get("updated_at")
        next_refresh_at = opp_card.get("next_refresh_at")
    else:
        items = []; updated_at = None; next_refresh_at = None

    data = (items or [])[:limit]
    if data:
        return _j({
            "company": name,
            "company_id": company_id,
            "history_id": history_id,
            "count": len(data),
            "opportunities": data,
            "updated_at": updated_at,
            "next_refresh_at": next_refresh_at,
        }, 200)
    return _j({
        "company": name,
        "company_id": company_id,
        "history_id": history_id,
        "count": 0,
        "opportunities": [],
        "message": "opportunities.run invoked. No card data found yet.",
    }, 200)

@api_bp.route("/company/upsert/", methods=["POST"])
def upsert_company():
    try:
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        desc = (data.get("description") or "").strip()
        comps = data.get("competitors", []) or []
        if not name:
            return _j({"error": "name is required"}, 400)
        if not isinstance(comps, list):
            return _j({"error": "competitors must be a list of strings"}, 400)

        from db.persist import upsert_company_profile, get_mongo_db
        upsert_company_profile({"name": name, "description": desc, "competitors": comps})

        db = get_mongo_db()
        doc = db["company_profiles"].find_one({"name": name})
        if not doc:
            return _j({"error": "failed to read back profile"}, 500)

        return _j({
            "id": str(doc.get("_id")),
            "name": doc.get("name"),
            "description": doc.get("description"),
            "competitors": doc.get("competitors", []),
            "created_at": doc.get("created_at"),
            "cards": doc.get("cards", {}),
        }, 200)

    except Exception as e:
        logger.exception("upsert_company error: %s", e)
        return _j({"error": str(e)}, 500)

@api_bp.route("/companies/", methods=["GET"])
def list_companies():
    try:
        db = get_mongo_db()
        q = (request.args.get("q") or "").strip()
        try:
            page = max(1, int(request.args.get("page", 1)))
        except Exception:
            page = 1
        try:
            page_size = max(1, min(100, int(request.args.get("page_size", 20))))
        except Exception:
            page_size = 20
        sort_field = (request.args.get("sort") or "name").strip()
        if sort_field not in {"name", "created_at"}:
            sort_field = "name"
        order = (request.args.get("order") or "asc").strip().lower()
        order_val = 1 if order == "asc" else -1

        filt = {}
        if q:
            filt = {"$or": [
                {"name": {"$regex": q, "$options": "i"}},
                {"description": {"$regex": q, "$options": "i"}},
            ]}

        total = db["company_profiles"].count_documents(filt)
        cursor = (
            db["company_profiles"]
            .find(filt)
            .sort(sort_field, order_val)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        items = []
        for d in cursor:
            items.append({
                "id": str(d.get("_id")),
                "name": d.get("name"),
                "description": d.get("description"),
                "competitors": d.get("competitors", []),
                "created_at": d.get("created_at"),
            })
        return _j({"page": page, "page_size": page_size, "total": total, "items": items}, 200)
    except Exception as e:
        logger.exception("list_companies error: %s", e)
        return _j({"error": str(e)}, 500)

@api_bp.route("/company/", methods=["GET"])
def get_company():
    name = (request.args.get("name") or "").strip() or None
    try:
        doc = get_company_profile(name=name)
        if not doc:
            return _j({"error": "company profile not found"}, 404)

        def _default_cards():
            now = datetime.now(timezone.utc)
            next_week = now + timedelta(days=7)
            nx = next_week.isoformat().replace("+00:00", "Z")
            return {
                "trending":     {"data": [], "updated_at": None, "next_refresh_at": nx},
                "newsfeed":     {"data": [], "updated_at": None, "next_refresh_at": nx},
                "ideas":        {"data": [], "updated_at": None, "next_refresh_at": nx},
                "backlinks":    {"data": [], "updated_at": None, "next_refresh_at": nx},
                "opportunities":{"data": [], "updated_at": None, "next_refresh_at": nx},
                "new_competitors": {"data": [], "updated_at": None, "next_refresh_at": nx},
            }

        cards = doc.get("cards") or _default_cards()
        return _j({
            "id": str(doc.get("_id")),
            "name": doc.get("name"),
            "description": doc.get("description"),
            "competitors": doc.get("competitors", []),
            "created_at": doc.get("created_at"),
            "cards": cards,
        }, 200)
    except Exception as e:
        logger.exception("get_company error: %s", e)
        return _j({"error": str(e)}, 500)
