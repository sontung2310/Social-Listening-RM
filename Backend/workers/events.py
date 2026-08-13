"""Validate DCT-shaped raw_collected envelopes for the AI worker."""
from __future__ import annotations

import logging
from typing import Any, Dict, Set

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS: Set[int] = {1}
CONTENT_POST = "post"
CONTENT_COMMENT = "comment"
EVENT_RAW_COLLECTED = "raw_collected"
SUPPORTED_CONTENT_TYPES = {CONTENT_POST, CONTENT_COMMENT}


class EventValidationError(ValueError):
    """Raised when an AI-queue message fails schema checks."""


def validate_event(msg: Any) -> Dict[str, Any]:
    """
    Validate a raw_collected event (same contract as Data-Crawler-Task events.py).

    Required: schema_version in {1}, content_type in {post,comment},
    non-empty source + external_id, payload object or null.
    """
    logger.info("[Validate] start")
    if not isinstance(msg, dict):
        raise EventValidationError("event must be an object")

    version = msg.get("schema_version")
    try:
        version_int = int(version)
    except (TypeError, ValueError):
        raise EventValidationError(f"invalid schema_version: {version!r}") from None
    if version_int not in SUPPORTED_SCHEMA_VERSIONS:
        raise EventValidationError(f"unsupported schema_version: {version_int}")

    content_type = (msg.get("content_type") or "").strip()
    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise EventValidationError(f"invalid content_type: {content_type!r}")

    source = (msg.get("source") or "").strip()
    if not source:
        raise EventValidationError("source is required")

    external_id = (msg.get("external_id") or "").strip()
    if not external_id:
        raise EventValidationError("external_id is required")

    payload = msg.get("payload")
    if payload is not None and not isinstance(payload, dict):
        raise EventValidationError("payload must be an object or null")

    event_type = (msg.get("event_type") or EVENT_RAW_COLLECTED).strip()
    if event_type and event_type != EVENT_RAW_COLLECTED:
        raise EventValidationError(f"unsupported event_type: {event_type!r}")

    logger.info(
        "[Validate] OK event_type=%s content_type=%s source=%s external_id=%s history_id=%s",
        event_type or EVENT_RAW_COLLECTED,
        content_type,
        source,
        external_id,
        msg.get("history_id"),
    )
    return msg
