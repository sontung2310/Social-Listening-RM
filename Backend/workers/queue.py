"""Queue backends for the AI worker (sim + real AWS SQS)."""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)

SAMPLE_MESSAGES_DIR = Path(__file__).resolve().parent / "sample_messages"
SAMPLE_INPUT_DIR = SAMPLE_MESSAGES_DIR / "input"
SAMPLE_OUTPUT_DIR = SAMPLE_MESSAGES_DIR / "output"


class QueueBackend(Protocol):
    def receive(self, max_messages: int = 1) -> List[Dict[str, Any]]:
        """Return messages as [{receipt_handle, body, sample_name?}, ...]."""

    def delete(self, receipt_handle: str) -> None:
        """Ack / remove a message."""

    def push(self, body: Dict[str, Any], sample_name: Optional[str] = None) -> str:
        """Enqueue a message. Returns receipt_handle."""


class SimulatedQueue:
    """In-memory stand-in for SQS crawl.ai.queue.

    Loads DCT-shaped samples from sample_messages/input/. receive() returns
    pending messages; delete() removes them.
    """

    def __init__(self, input_dir: Optional[Path] = None, load_samples: bool = True):
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._meta: Dict[str, Dict[str, Any]] = {}
        self._dlq: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = []
        if load_samples:
            self._load_samples(input_dir or SAMPLE_INPUT_DIR)

    def _load_samples(self, directory: Path) -> None:
        if not directory.is_dir():
            logger.warning("[Queue] Sample input dir missing: %s", directory)
            return
        paths = sorted(directory.glob("*.json"))
        logger.info("[Queue] Loading %s sample message(s) from %s", len(paths), directory)
        for path in paths:
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
                handle = self.push(body, sample_name=path.stem)
                logger.info(
                    "[Queue] Loaded input sample name=%s source=%s content_type=%s handle=%s",
                    path.stem,
                    body.get("source"),
                    body.get("content_type"),
                    handle[:8],
                )
            except Exception as e:
                logger.exception("[Queue] Failed to load sample %s: %s", path, e)

    def push(self, body: Dict[str, Any], sample_name: Optional[str] = None) -> str:
        handle = str(uuid.uuid4())
        self._pending[handle] = body
        self._meta[handle] = {"sample_name": sample_name}
        self._order.append(handle)
        return handle

    def receive(self, max_messages: int = 1) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for handle in list(self._order):
            if len(out) >= max(1, max_messages):
                break
            if handle not in self._pending:
                continue
            meta = self._meta.get(handle) or {}
            out.append(
                {
                    "receipt_handle": handle,
                    "body": self._pending[handle],
                    "sample_name": meta.get("sample_name"),
                }
            )
        logger.info("[Queue] receive(max=%s) → %s message(s)", max_messages, len(out))
        return out

    def delete(self, receipt_handle: str) -> None:
        self._pending.pop(receipt_handle, None)
        self._meta.pop(receipt_handle, None)
        if receipt_handle in self._order:
            self._order.remove(receipt_handle)
        self._dlq.pop(receipt_handle, None)
        logger.info("[Queue] delete ack handle=%s", receipt_handle[:8])

    def fail(self, receipt_handle: str) -> None:
        """Move message to a local DLQ list (simulates redrive)."""
        body = self._pending.pop(receipt_handle, None)
        meta = self._meta.pop(receipt_handle, None)
        if receipt_handle in self._order:
            self._order.remove(receipt_handle)
        if body is not None:
            self._dlq[receipt_handle] = body
            logger.warning(
                "[Queue] moved to local DLQ handle=%s sample=%s",
                receipt_handle[:8],
                (meta or {}).get("sample_name"),
            )

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def dlq_count(self) -> int:
        return len(self._dlq)


class SqsQueue:
    """Real AWS SQS backend for social_listening_crawling_response (AI queue)."""

    def __init__(self, queue_url: Optional[str] = None, wait_time_seconds: Optional[int] = None):
        import config
        from sqs_client import sqs_client

        self._queue_url = (queue_url or config.SQS_AI_QUEUE_URL or "").strip()
        if not self._queue_url:
            raise RuntimeError("SQS_AI_QUEUE_URL is not set")
        self._wait = (
            wait_time_seconds
            if wait_time_seconds is not None
            else int(getattr(config, "SQS_WAIT_TIME_SECONDS", 20))
        )
        self._wait = max(0, min(20, self._wait))
        self._client = sqs_client()
        logger.info("[Queue] backend=sqs url=%s wait=%ss", self._queue_url, self._wait)

    def receive(self, max_messages: int = 1) -> List[Dict[str, Any]]:
        n = max(1, min(10, int(max_messages)))
        resp = self._client.receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=n,
            WaitTimeSeconds=self._wait,
            VisibilityTimeout=60,
        )
        out: List[Dict[str, Any]] = []
        for msg in resp.get("Messages") or []:
            raw = msg.get("Body") or "{}"
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                logger.exception("[Queue] invalid JSON body message_id=%s", msg.get("MessageId"))
                continue
            out.append(
                {
                    "receipt_handle": msg["ReceiptHandle"],
                    "body": body,
                }
            )
        logger.info("[Queue] sqs receive(max=%s) → %s message(s)", n, len(out))
        return out

    def delete(self, receipt_handle: str) -> None:
        self._client.delete_message(QueueUrl=self._queue_url, ReceiptHandle=receipt_handle)
        logger.info("[Queue] sqs delete ack handle=%s", receipt_handle[:12])

    def push(self, body: Dict[str, Any], sample_name: Optional[str] = None) -> str:
        resp = self._client.send_message(
            QueueUrl=self._queue_url,
            MessageBody=json.dumps(body, default=str),
        )
        mid = resp.get("MessageId") or ""
        logger.info("[Queue] sqs push message_id=%s sample=%s", mid, sample_name)
        return mid


def get_queue():
    """Factory — sim or sqs."""
    import config

    backend = (getattr(config, "AI_QUEUE_BACKEND", None) or "sim").strip().lower()
    if backend == "sim":
        logger.info("[Queue] backend=sim input_dir=%s", SAMPLE_INPUT_DIR)
        return SimulatedQueue()
    if backend == "sqs":
        return SqsQueue()
    raise NotImplementedError(f"AI_QUEUE_BACKEND={backend!r} not supported; use 'sim' or 'sqs'.")
