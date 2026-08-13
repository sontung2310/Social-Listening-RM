"""Cloud Mongo upserts for AI-enriched posts/comments (architecture: ai_posts / ai_comments)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from db.persist import get_mongo_db

logger = logging.getLogger(__name__)

_INDEXES_READY = False


def ensure_ai_indexes() -> None:
    """Create unique (source, external_id) indexes once per process."""
    global _INDEXES_READY
    if _INDEXES_READY:
        return
    db = get_mongo_db()
    for name in ("ai_posts", "ai_comments"):
        db[name].create_index(
            [("source", 1), ("external_id", 1)],
            unique=True,
            name="uniq_source_external_id",
        )
    logger.info("[CloudDB] indexes ready on ai_posts / ai_comments")
    _INDEXES_READY = True


def _now() -> datetime:
    return datetime.now(timezone.utc)


def upsert_ai_post(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert into ai_posts by (source, external_id). Returns write summary."""
    return _upsert("ai_posts", doc)


def upsert_ai_comment(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert into ai_comments by (source, external_id). Returns write summary."""
    return _upsert("ai_comments", doc)


def _upsert(collection: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    ensure_ai_indexes()
    source = (doc.get("source") or "").strip()
    external_id = (doc.get("external_id") or "").strip()
    if not source or not external_id:
        raise ValueError("source and external_id are required for AI upsert")

    now = _now()
    body = dict(doc)
    body["source"] = source
    body["external_id"] = external_id
    body["updated_at"] = now
    if "processed_at" not in body or body.get("processed_at") is None:
        body["processed_at"] = now

    logger.info(
        "[CloudDB] writing %s key=(%s, %s) sentiment=%s topics=%s",
        collection,
        source,
        external_id,
        (body.get("sentiment") or {}).get("label"),
        body.get("topics"),
    )

    db = get_mongo_db()
    res = db[collection].update_one(
        {"source": source, "external_id": external_id},
        {"$set": body, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    info = {
        "collection": collection,
        "source": source,
        "external_id": external_id,
        "upserted": res.upserted_id is not None,
        "matched": res.matched_count,
        "modified": res.modified_count,
    }
    logger.info("[CloudDB] write result %s", info)
    return info
