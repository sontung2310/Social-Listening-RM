"""Crawl Management API — accept jobs and forward to DCT via SQS command queue.

Supports typed content_crawl and influencer_discovery requests.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional, Set, Tuple, Union

from bson import ObjectId
from flask import Blueprint, jsonify, make_response, request
import requests

import config
from db.persist import get_mongo_db
from publishers.command_sqs import publish_crawl_command

logger = logging.getLogger(__name__)

# Match Data-Crawler-Task sources.CATEGORIES
ALLOWED_SOURCES: Set[str] = {"x", "reddit", "youtube", "duckduckgo", "news", "all"}
DEFAULT_LIMIT = 50
DEFAULT_SOURCE = "all"
TASK_CONTENT = "content_crawl"
TASK_INFLUENCER = "influencer_discovery"


def _parse_influencer_input(raw_input: dict) -> tuple[Optional[dict], Optional[tuple]]:
    required = (
        "company_id",
        "company_name",
        "company_domain",
        "company_summary",
        "field",
        "related_terms",
        "platform",
        "limit",
    )
    missing = [name for name in required if name not in raw_input]
    if missing:
        return None, ({"error": f"missing required influencer fields: {', '.join(missing)}"}, 400)

    company_id = str(raw_input.get("company_id") or "").strip()
    company_name = " ".join(str(raw_input.get("company_name") or "").split())
    company_domain = str(raw_input.get("company_domain") or "").strip().lower()
    company_summary = " ".join(str(raw_input.get("company_summary") or "").split())
    field = " ".join(str(raw_input.get("field") or "").split())
    platform = str(raw_input.get("platform") or "").strip().lower()
    related_terms = raw_input.get("related_terms")
    if not company_id:
        return None, ({"error": "company_id is required"}, 400)
    if not company_name:
        return None, ({"error": "company_name is required"}, 400)
    if not re.fullmatch(r"[a-z0-9.-]+", company_domain):
        return None, ({"error": "company_domain must be a valid domain"}, 422)
    if not company_summary:
        return None, ({"error": "company_summary is required"}, 400)
    if not field:
        return None, ({"error": "field is required"}, 400)
    if not isinstance(related_terms, list):
        return None, ({"error": "related_terms must be an array"}, 422)
    related_terms = [" ".join(str(term).split()) for term in related_terms if str(term).strip()]
    if not related_terms:
        return None, ({"error": "related_terms must contain at least one term"}, 422)
    if platform != "x":
        return None, ({"error": "only platform x is currently implemented"}, 422)
    try:
        limit = int(raw_input["limit"])
    except (TypeError, ValueError):
        return None, ({"error": "limit must be an integer"}, 400)
    if limit < 1 or limit > 100:
        return None, ({"error": "limit must be between 1 and 100"}, 422)

    return {
        "company_id": company_id,
        "company_name": company_name,
        "company_domain": company_domain,
        "company_summary": company_summary,
        "field": field,
        "related_terms": related_terms,
        "platform": platform,
        "limit": limit,
        "resume": bool(raw_input.get("resume", False)),
    }, None


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
    task_type = (data.get("task_type") or TASK_CONTENT).strip().lower()
    if task_type not in {TASK_CONTENT, TASK_INFLUENCER}:
        return None, ({"error": "unknown task_type"}, 422)
    raw_input = data.get("input", data)
    if not isinstance(raw_input, dict):
        return None, ({"error": "input must be an object"}, 400)

    if task_type == TASK_INFLUENCER:
        parsed_influencer, error = _parse_influencer_input(raw_input)
        if error:
            return None, error
        assert parsed_influencer is not None
        return {"task_type": task_type, "input": parsed_influencer}, None

    query = (raw_input.get("query") or "").strip()
    if not query:
        return None, ({"error": "query is required"}, 400)

    raw_source = raw_input.get("source", DEFAULT_SOURCE)
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

    time_delta: Optional[Union[int, str]] = raw_input.get("time_delta")
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
        limit = int(raw_input.get("limit", DEFAULT_LIMIT))
    except (TypeError, ValueError):
        return None, ({"error": "limit must be an integer"}, 400)
    if limit < 1 or limit > 100:
        return None, ({"error": "limit must be between 1 and 100"}, 422)

    return (
        {
            "task_type": task_type,
            "input": {
                "query": query,
                "source": source,
                "time_delta": time_delta,
                "limit": limit,
            },
        },
        None,
    )


def register_crawl_routes(api_bp: Blueprint) -> None:
    @api_bp.route("/crawl/", methods=["POST"])
    def start_crawl():
        """Publish a typed content or influencer command to Data-Crawler-Task."""
        data = request.get_json(silent=True) or {}
        parsed, err = _parse_crawl_body(data)
        if err:
            payload, status = err
            return _j(payload, status)

        assert parsed is not None
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        task_type = parsed["task_type"]
        input_data = parsed["input"]
        doc: dict[str, Any] = {
            "job_id": job_id,
            "status": "accepted",
            "task_type": task_type,
            **input_data,
            "created_at": now,
            "updated_at": now,
        }
        if task_type == TASK_INFLUENCER:
            # The command uses the API job id as the DCT task id. Keep the
            # ownership explicit in the Pace record for status/audit tooling.
            doc["dct_task_id"] = job_id

        try:
            db = get_mongo_db()
            db["crawl_jobs"].insert_one(doc)
        except Exception as e:
            logger.exception("crawl_jobs insert failed: %s", e)
            return _j({"error": f"cannot persist crawl job: {e}"}, 503)

        try:
            publish_crawl_command(
                job_id=job_id,
                task_type=task_type,
                input_data=input_data,
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
            "[CrawlAPI] accepted job_id=%s task_type=%s input=%s",
            job_id,
            task_type,
            {key: value for key, value in input_data.items() if key != "company_summary"},
        )
        return _j(
            {
                "job_id": job_id,
                "status": "accepted",
                "task_type": task_type,
                **input_data,
            },
            202,
        )

    @api_bp.route("/crawl/<job_id>/", methods=["GET"])
    def crawl_job_status(job_id: str):
        """Return DCT-authoritative status for influencer jobs."""
        try:
            db = get_mongo_db()
            doc = db["crawl_jobs"].find_one({"job_id": job_id}, {"_id": 0})
        except Exception as e:
            logger.exception("crawl_jobs lookup failed: %s", e)
            return _j({"error": str(e)}, 503)
        if not doc:
            return _j({"error": "not found"}, 404)
        if doc.get("task_type") == TASK_INFLUENCER:
            dct_task_id = doc.get("dct_task_id") or job_id
            headers = {"X-API-Key": config.DCT_API_KEY} if config.DCT_API_KEY else {}
            try:
                response = requests.get(
                    f"{config.DCT_API_BASE_URL}/crawl/{dct_task_id}",
                    headers=headers,
                    timeout=config.DCT_API_TIMEOUT_SECONDS,
                )
                if response.status_code == 404:
                    return _j({"error": "DCT task not found", "job_id": job_id, "dct_task_id": dct_task_id}, 404)
                response.raise_for_status()
                status = response.json()
                status["job_id"] = job_id
                status["dct_task_id"] = dct_task_id
                status["task_type"] = TASK_INFLUENCER
                return _j(status, 200)
            except requests.RequestException as exc:
                logger.warning("event=influencer.status_upstream_unavailable job_id=%s reason=%s", job_id, exc)
                return _j({"error": "DCT status unavailable", "job_id": job_id}, 503)
        return _j(doc, 200)
