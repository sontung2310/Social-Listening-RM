"""Crawl Management API — accept jobs and forward to DCT via SQS command queue.

Request body mirrors Data-Crawler-Task `CrawlRequest`:
  query (required), source, time_delta, limit
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional, Set, Tuple, Union

from bson import ObjectId
from flask import Blueprint, jsonify, make_response, request

from db.persist import get_mongo_db
from publishers.command_sqs import publish_crawl_command

logger = logging.getLogger(__name__)

# Match Data-Crawler-Task sources.CATEGORIES
ALLOWED_SOURCES: Set[str] = {"x", "reddit", "youtube", "duckduckgo", "news", "all"}
DEFAULT_LIMIT = 50
DEFAULT_SOURCE = "all"


def _json_safe(obj: Any):
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
    return make_response(jsonify(_json_safe(payload)), status_code)


def _parse_crawl_body(data: dict) -> Tuple[Optional[dict], Optional[tuple]]:
    """
    Validate DCT-shaped body.

    Returns (parsed, None) or (None, (error_payload, status)).
    """
    query = (data.get("query") or "").strip()
    if not query:
        return None, ({"error": "query is required"}, 400)

    raw_source = data.get("source", DEFAULT_SOURCE)
    if raw_source is None or (isinstance(raw_source, str) and not raw_source.strip()):
        source = DEFAULT_SOURCE
    else:
        source = str(raw_source).strip().lower()
    if source not in ALLOWED_SOURCES:
        return None, (
            {
                "error": f"unknown source {raw_source!r}",
                "allowed": sorted(ALLOWED_SOURCES),
            },
            422,
        )

    time_delta: Optional[Union[int, str]] = data.get("time_delta")
    if time_delta is not None and time_delta != "":
        if isinstance(time_delta, bool):
            return None, ({"error": "invalid time_delta"}, 422)
        if isinstance(time_delta, (int, float)) and not isinstance(time_delta, bool):
            time_delta = int(time_delta)
        else:
            time_delta = str(time_delta).strip()
            if time_delta.isdigit():
                time_delta = int(time_delta)
    else:
        time_delta = None

    try:
        limit = int(data.get("limit", DEFAULT_LIMIT))
    except (TypeError, ValueError):
        return None, ({"error": "limit must be an integer"}, 400)
    if limit < 1 or limit > 100:
        return None, ({"error": "limit must be between 1 and 100"}, 422)

    return (
        {
            "query": query,
            "source": source,
            "time_delta": time_delta,
            "limit": limit,
        },
        None,
    )


def register_crawl_routes(api_bp: Blueprint) -> None:
    @api_bp.route("/crawl/", methods=["POST"])
    def start_crawl():
        """Forward a crawl command to DCT via SQS (same fields as DCT POST /crawl)."""
        data = request.get_json(silent=True) or {}
        parsed, err = _parse_crawl_body(data)
        if err:
            payload, status = err
            return _j(payload, status)

        assert parsed is not None
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "job_id": job_id,
            "status": "accepted",
            "query": parsed["query"],
            "source": parsed["source"],
            "time_delta": parsed["time_delta"],
            "limit": parsed["limit"],
            "created_at": now,
            "updated_at": now,
        }

        try:
            db = get_mongo_db()
            db["crawl_jobs"].insert_one(doc)
        except Exception as e:
            logger.exception("crawl_jobs insert failed: %s", e)
            return _j({"error": f"cannot persist crawl job: {e}"}, 503)

        try:
            publish_crawl_command(
                job_id=job_id,
                query=parsed["query"],
                source=parsed["source"],
                time_delta=parsed["time_delta"],
                limit=parsed["limit"],
            )
        except Exception as e:
            logger.exception("SQS command publish failed job_id=%s: %s", job_id, e)
            try:
                db["crawl_jobs"].update_one(
                    {"job_id": job_id},
                    {
                        "$set": {
                            "status": "publish_failed",
                            "error": str(e),
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                )
            except Exception:
                pass
            return _j(
                {"error": f"failed to publish crawl command: {e}", "job_id": job_id},
                502,
            )

        logger.info(
            "[CrawlAPI] accepted job_id=%s query=%r source=%s limit=%s",
            job_id,
            parsed["query"],
            parsed["source"],
            parsed["limit"],
        )
        return _j(
            {
                "job_id": job_id,
                "status": "accepted",
                "query": parsed["query"],
                "source": parsed["source"],
                "time_delta": parsed["time_delta"],
                "limit": parsed["limit"],
            },
            202,
        )

    @api_bp.route("/crawl/<job_id>/", methods=["GET"])
    def crawl_job_status(job_id: str):
        """Return crawl_jobs row for polling."""
        try:
            db = get_mongo_db()
            doc = db["crawl_jobs"].find_one({"job_id": job_id}, {"_id": 0})
        except Exception as e:
            logger.exception("crawl_jobs lookup failed: %s", e)
            return _j({"error": str(e)}, 503)
        if not doc:
            return _j({"error": "not found"}, 404)
        return _j(doc, 200)
