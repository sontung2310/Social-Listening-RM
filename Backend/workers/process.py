"""Process one raw_collected article message: AI enrichment then cloud upsert."""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from db.ai_store import upsert_ai_comment, upsert_ai_post
from workers.events import CONTENT_COMMENT, CONTENT_POST, validate_event
from workers.sample_io import write_sample_output

logger = logging.getLogger(__name__)


def _extract_text(payload: Dict[str, Any]) -> str:
    text = (payload.get("text") or "").strip()
    if text:
        return text
    return (payload.get("title") or "").strip()


def _preview(text: str, limit: int = 160) -> str:
    flat = " ".join((text or "").split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1] + "…"


def _long_chars() -> int:
    try:
        return int(os.getenv("NLP_LONG_CHARS") or "4000")
    except ValueError:
        return 4000


# Persisted nlp_meta — keep only provider/model identity.
_STORED_NLP_META_KEYS = (
    "provider",
    "model",
)


def _stored_nlp_meta(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = meta or {}
    out: Dict[str, Any] = {}
    for key in _STORED_NLP_META_KEYS:
        if key in raw and raw[key] is not None:
            out[key] = raw[key]
    return out


def build_ai_document(event: Dict[str, Any], enrichment: Dict[str, Any]) -> Dict[str, Any]:
    payload = event.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    content_type = (event.get("content_type") or "").strip()
    text = _extract_text(payload)
    now = datetime.now(timezone.utc)
    meta = _stored_nlp_meta(enrichment.get("nlp_meta") or {})

    query = payload.get("query")
    if query is not None and not isinstance(query, str):
        query = str(query)
    if isinstance(query, str):
        query = query.strip() or None

    doc: Dict[str, Any] = {
        "source": (event.get("source") or "").strip(),
        "external_id": (event.get("external_id") or "").strip(),
        "event_id": event.get("event_id"),
        "history_id": event.get("history_id"),
        "content_type": content_type,
        "query": query,
        "url": payload.get("url") or payload.get("parent_content_url"),
        "title": (payload.get("title") or "") if content_type == CONTENT_POST else "",
        "text": text,
        "author": payload.get("author"),
        "published_ts": payload.get("published_ts"),
        "crawled_at": payload.get("crawled_at"),
        "engagement": payload.get("engagement"),
        "parent_content_id": event.get("parent_content_id") or payload.get("parent_content_id"),
        "payload": payload,
        "sentiment": enrichment.get("sentiment") or {"label": "neutral", "score": 0.0},
        "topics": enrichment.get("topics") or ["Other"],
        "topic_confidence": float(enrichment.get("topic_confidence") or 0.0),
        "keywords": enrichment.get("keywords") or [],
        "summary": enrichment.get("summary") or "",
        "nlp_meta": meta,
        "processed_at": now,
    }
    return doc


def _upsert_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    content_type = doc["content_type"]
    if content_type == CONTENT_COMMENT:
        return upsert_ai_comment(doc)
    return upsert_ai_post(doc)


def _async_enrich_long(
    event: Dict[str, Any],
    text: str,
    *,
    sample_name: Optional[str] = None,
) -> None:
    """Background chunked enrichment; patches ai_* document when ready."""
    try:
        from ai.enrichment.pipeline import enrich_text

        logger.info(
            "[NLP:Async] START source=%s external_id=%s chars=%s",
            event.get("source"),
            event.get("external_id"),
            len(text),
        )
        result = enrich_text(
            text,
            source=(event.get("source") or ""),
            external_id=(event.get("external_id") or ""),
            content_type=(event.get("content_type") or ""),
            force_sync=True,
        )
        doc = build_ai_document(event, result.to_dict())
        write_info = _upsert_doc(doc)
        write_sample_output(sample_name, doc)
        logger.info("[NLP:Async] DONE write=%s nlp_status=%s", write_info, (doc.get("nlp_meta") or {}).get("nlp_status"))
    except Exception:
        logger.exception("[NLP:Async] FAILED source=%s", event.get("source"))


def process_event(
    raw: Dict[str, Any],
    *,
    persist: bool = True,
    sample_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Validate → LLM enrichment → upsert ai_posts / ai_comments.

    Long texts (>= NLP_LONG_CHARS): upsert pending stub, then async chunked enrich.
    """
    logger.info(
        "[Process] START sample=%s keys=%s",
        sample_name,
        list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__,
    )

    event = validate_event(raw)
    payload = event.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    text = _extract_text(payload)
    logger.info(
        "[NLP] START content_type=%s source=%s text_chars=%s title=%r",
        event.get("content_type"),
        event.get("source"),
        len(text),
        _preview(str(payload.get("title") or ""), 80),
    )

    from ai.enrichment.pipeline import enrich_text, pending_stub_result

    defer_long = len(text) >= _long_chars()
    if defer_long:
        enrichment = pending_stub_result(text).to_dict()
        logger.info("[NLP] DEFER long text → pending stub chars=%s", len(text))
    else:
        result = enrich_text(
            text,
            source=(event.get("source") or ""),
            external_id=(event.get("external_id") or ""),
            content_type=(event.get("content_type") or ""),
        )
        enrichment = result.to_dict()

    logger.info(
        "[NLP] DONE sentiment=%s topics=%s keywords=%s summary_preview=%r nlp_status=%s",
        (enrichment.get("sentiment") or {}).get("label"),
        enrichment.get("topics"),
        len(enrichment.get("keywords") or []),
        _preview(enrichment.get("summary") or ""),
        (enrichment.get("nlp_meta") or {}).get("nlp_status"),
    )

    doc = build_ai_document(event, enrichment)
    content_type = doc["content_type"]

    write_info: Optional[Dict[str, Any]] = None
    if persist:
        logger.info(
            "[CloudDB] START upsert collection=%s source=%s external_id=%s",
            "ai_comments" if content_type == CONTENT_COMMENT else "ai_posts",
            doc["source"],
            doc["external_id"],
        )
        write_info = _upsert_doc(doc)
        logger.info("[CloudDB] DONE write=%s", write_info)

    output_path = write_sample_output(sample_name, doc)

    if defer_long and persist:
        t = threading.Thread(
            target=_async_enrich_long,
            args=(event, text),
            kwargs={"sample_name": sample_name},
            daemon=True,
            name="nlp-async-enrich",
        )
        t.start()
        logger.info("[NLP] spawned async enrich thread")

    logger.info(
        "[Process] DONE sample=%s content_type=%s source=%s external_id=%s output=%s",
        sample_name,
        content_type,
        doc["source"],
        doc["external_id"],
        output_path,
    )

    return {
        "ok": True,
        "content_type": content_type,
        "source": doc["source"],
        "external_id": doc["external_id"],
        "sentiment": doc.get("sentiment"),
        "topics": doc.get("topics"),
        "keywords": doc.get("keywords"),
        "summary": doc.get("summary"),
        "nlp_meta": doc.get("nlp_meta"),
        "write": write_info,
        "doc": doc,
        "output_path": str(output_path) if output_path else None,
    }
