"""Publish crawl commands to SQS command queue."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import config
from sqs_client import sqs_client

logger = logging.getLogger(__name__)


def publish_crawl_command(
    *,
    job_id: str,
    query: str,
    source: Optional[str] = None,
    time_delta: Optional[Any] = None,
    limit: int = 50,
) -> None:
    url = config.SQS_COMMAND_QUEUE_URL
    if not url:
        raise RuntimeError("SQS_COMMAND_QUEUE_URL is not set")

    body: Dict[str, Any] = {
        "schema_version": 1,
        "command_type": "start_crawl",
        "job_id": job_id,
        "query": query,
        "source": source,
        "time_delta": time_delta,
        "limit": limit,
    }
    client = sqs_client()
    client.send_message(QueueUrl=url, MessageBody=json.dumps(body, default=str))
    logger.info("[CommandSQS] published job_id=%s query=%r source=%s", job_id, query, source)
