"""AI worker consumer loop — simulated SQS → process → ack."""
from __future__ import annotations

import logging
import time
from typing import Optional

import config
from workers.process import process_event
from workers.events import EVENT_RAW_COLLECTED
from workers.queue import QueueBackend, SimulatedQueue, get_queue

logger = logging.getLogger(__name__)

LEGACY_INFLUENCER_CONTENT_TYPE = "influencer"


def handle_message(
    queue: QueueBackend,
    receipt_handle: str,
    body: dict,
    sample_name: Optional[str] = None,
) -> bool:
    """Process one message; delete on success. Returns True if acked."""
    logger.info(
        "[Consumer] ===== message BEGIN handle=%s sample=%s source=%s content_type=%s =====",
        receipt_handle[:8],
        sample_name,
        body.get("source") if isinstance(body, dict) else None,
        body.get("content_type") if isinstance(body, dict) else None,
    )
    try:
        event_type = (body.get("event_type") or EVENT_RAW_COLLECTED).strip()
        content_type = (body.get("content_type") or "").strip()
        if event_type == EVENT_RAW_COLLECTED and content_type == LEGACY_INFLUENCER_CONTENT_TYPE:
            # The retired influencer response path used the same raw event name
            # as content. Discard only that distinguishable legacy shape.
            logger.warning(
                "[Consumer] ===== message DISCARD legacy influencer event_type=%s handle=%s "
                "sample=%s source=%s content_type=%s =====",
                event_type,
                receipt_handle[:8],
                sample_name,
                body.get("source"),
                body.get("content_type"),
            )
            queue.delete(receipt_handle)
            logger.info(
                "[Consumer] ===== message ACK legacy event_type=%s handle=%s =====",
                event_type,
                receipt_handle[:8],
            )
            return True
        if event_type not in {EVENT_RAW_COLLECTED, "article_collected"}:
            raise ValueError(f"unsupported event_type: {event_type!r}")
        result = process_event(body, persist=True, sample_name=sample_name)
        queue.delete(receipt_handle)
        logger.info(
            "[Consumer] ===== message ACK sample=%s %s:%s sentiment=%s topics=%s output=%s =====",
            sample_name,
            result.get("source"),
            result.get("external_id"),
            (result.get("sentiment") or {}).get("label"),
            result.get("topics"),
            result.get("output_path"),
        )
        return True
    except Exception as e:
        logger.exception(
            "[Consumer] ===== message FAIL handle=%s sample=%s error=%s =====",
            receipt_handle[:8],
            sample_name,
            e,
        )
        if isinstance(queue, SimulatedQueue):
            pass
        return False


def run_once(queue: Optional[QueueBackend] = None, max_messages: Optional[int] = None) -> int:
    """Receive and process up to max_messages, then return count processed."""
    q = queue or get_queue()
    limit = max_messages if max_messages is not None else config.AI_WORKER_MAX_MESSAGES
    logger.info("[Consumer] run_once start max_messages=%s pending≈%s", limit, getattr(q, "pending_count", "?"))
    messages = q.receive(max_messages=limit)
    if not messages:
        logger.info("[Consumer] No messages pending")
        return 0
    ok = 0
    for msg in messages:
        if handle_message(
            q,
            msg["receipt_handle"],
            msg["body"],
            sample_name=msg.get("sample_name"),
        ):
            ok += 1
    logger.info("[Consumer] run_once done acked=%s / received=%s", ok, len(messages))
    return ok


def run_forever(queue: Optional[QueueBackend] = None) -> None:
    """Long-running loop (sim idle-sleeps when empty)."""
    q = queue or get_queue()
    logger.info(
        "[Consumer] run_forever started backend=%s max_messages=%s",
        config.AI_QUEUE_BACKEND,
        config.AI_WORKER_MAX_MESSAGES,
    )
    while True:
        messages = q.receive(max_messages=config.AI_WORKER_MAX_MESSAGES)
        if not messages:
            time.sleep(config.AI_WORKER_IDLE_SLEEP_SECONDS)
            continue
        for msg in messages:
            handle_message(
                q,
                msg["receipt_handle"],
                msg["body"],
                sample_name=msg.get("sample_name"),
            )
