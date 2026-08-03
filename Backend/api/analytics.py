import time
from bson import ObjectId
from db.persist import get_mongo_db

import requests
from datetime import datetime, timezone, timedelta

from db.persist import _iso_z, get_mongo_db, get_company_profile
def global_top_topics(days: int = 30, limit: int = 20):
    db = get_mongo_db()

    now_dt = datetime.now(timezone.utc)
    from_dt = now_dt - timedelta(days=days)

    pipeline = [
        {"$match": {"status": "done"}},

        {"$lookup": {
            "from": "history",
            "localField": "history_id",
            "foreignField": "_id",
            "as": "hist"
        }},
        {"$unwind": {"path": "$hist", "preserveNullAndEmptyArrays": False}},

        {"$match": {
            "hist.created_at": {"$gte": from_dt},
            "hist.subject": {"$type": "string", "$ne": ""}
        }},

        {"$set": {
            "norm_subject": {
                "$toLower": {
                    "$trim": {"input": "$hist.subject"}
                }
            }
        }},

        {"$group": {
            "_id": {"hid": "$hist._id", "sub": "$norm_subject"}
        }},

        {"$group": {
            "_id": "$_id.sub",
            "count": {"$sum": 1}
        }},

        {"$sort": {"count": -1}},
        {"$limit": max(1, int(limit))}
    ]

    rows = list(db["ai_results"].aggregate(pipeline))

    return [r["_id"] for r in rows]

def _as_list(val):
    """
    Accept list[str] or comma-separated str -> list[str]. Anything else -> [].
    """
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        return [s.strip() for s in val.split(",") if s.strip()]
    return []


def _parse_iso_to_date(s: str | None):
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt.astimezone(timezone.utc).date()
    except Exception:
        return None

def _coerce_topics_list(payload) -> list[str]:
    if isinstance(payload, list):
        return [str(x).strip() for x in payload if isinstance(x, str)]
    if isinstance(payload, dict) and isinstance(payload.get("topics"), list):
        return [str(x).strip() for x in payload["topics"] if isinstance(x, str)]
    return []












def _from_dt(days: int):
    return datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))

def trend_top_tags(history_id: ObjectId, days: int = 30, top_k: int = 20):
    db = get_mongo_db()
    from_dt = _from_dt(days)
    pipeline = [
        {"$match": {
            "history_id": history_id,
            "status": {"$in": ["queued", "done"]},   # include queued so it isn't empty early
            "tags": {"$type": "array", "$ne": []}
        }},
        # bring in history.created_at ONLY to build a fallback date window
        {"$lookup": {
            "from": "history",
            "localField": "history_id",
            "foreignField": "_id",
            "as": "hist"
        }},
        {"$addFields": {"hist": {"$first": "$hist"}}},
        # pub_dt = published_ts -> toDate; else fallback to history.created_at
        {"$addFields": {
            "pub_dt": {
                "$ifNull": [
                    {"$toDate": {"$multiply": ["$published_ts", 1000]}},
                    "$hist.created_at"
                ]
            }
        }},
        {"$match": {"pub_dt": {"$gte": from_dt}}},
        {"$unwind": {"path": "$tags", "preserveNullAndEmptyArrays": False}},
        {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": int(top_k)}
    ]
    return list(db["ai_results"].aggregate(pipeline))

def trend_timeseries_by_day(history_id: ObjectId, days: int = 30, tag: str | None = None):
    db = get_mongo_db()
    from_dt = _from_dt(days)
    pipeline = [
        {"$match": {
            "history_id": history_id,
            "status": {"$in": ["queued", "done"]}
        }},
        {"$lookup": {
            "from": "history",
            "localField": "history_id",
            "foreignField": "_id",
            "as": "hist"
        }},
        {"$addFields": {"hist": {"$first": "$hist"}}},
        {"$addFields": {
            "pub_dt": {
                "$ifNull": [
                    {"$toDate": {"$multiply": ["$published_ts", 1000]}},
                    "$hist.created_at"
                ]
            },
            "tags": {"$ifNull": ["$tags", []]}
        }},
        {"$match": {"pub_dt": {"$gte": from_dt}}},
    ]
    if tag:
        pipeline += [
            {"$unwind": {"path": "$tags", "preserveNullAndEmptyArrays": False}},
            {"$match": {"tags": tag}}
        ]
    pipeline += [
        {"$group": {
            "_id": {"$dateTrunc": {"date": "$pub_dt", "unit": "day"}},
            "count": {"$sum": 1},
            "avg_relevance": {"$avg": "$relevance_score"}
        }},
        {"$sort": {"_id": 1}}
    ]
    return list(db["ai_results"].aggregate(pipeline))

def trend_by_source(history_id: ObjectId, days: int = 30, tag: str | None = None):
    db = get_mongo_db()
    from_dt = _from_dt(days)
    pipeline = [
        {"$match": {
            "history_id": history_id,
            "status": {"$in": ["queued", "done"]}
        }},
        {"$lookup": {
            "from": "history",
            "localField": "history_id",
            "foreignField": "_id",
            "as": "hist"
        }},
        {"$addFields": {"hist": {"$first": "$hist"}}},
        {"$addFields": {
            "pub_dt": {
                "$ifNull": [
                    {"$toDate": {"$multiply": ["$published_ts", 1000]}},
                    "$hist.created_at"
                ]
            },
            "tags": {"$ifNull": ["$tags", []]}
        }},
        {"$match": {"pub_dt": {"$gte": from_dt}}},
    ]
    if tag:
        pipeline += [
            {"$unwind": {"path": "$tags", "preserveNullAndEmptyArrays": False}},
            {"$match": {"tags": tag}}
        ]
    pipeline += [
        {"$group": {
            "_id": "$source",
            "count": {"$sum": 1},
            "avg_relevance": {"$avg": "$relevance_score"}
        }},
        {"$sort": {"count": -1}}
    ]
    return list(db["ai_results"].aggregate(pipeline))