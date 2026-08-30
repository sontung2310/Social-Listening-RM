"""Publish crawl commands to SQS command queue."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

import config

logger = logging.getLogger(__name__)


def build_crawl_command(
    *, job_id: str, task_type: str, input_data: Dict[str, Any]
) -> Dict[str, Any]:
    return {
        "job_id": job_id,
        "task_type": task_type,
        "input": input_data,
    }


def publish_crawl_command(
    *,
    job_id: str,
    task_type: str,
    input_data: Dict[str, Any],
) -> None:
    from sqs_client import sqs_client

    url = config.SQS_COMMAND_QUEUE_URL
    if not url:
        raise RuntimeError("SQS_COMMAND_QUEUE_URL is not set")

    body = build_crawl_command(
        job_id=job_id, task_type=task_type, input_data=input_data
    )
    client = sqs_client()
    client.send_message(QueueUrl=url, MessageBody=json.dumps(body, default=str))
    logger.info("[CommandSQS] published job_id=%s task_type=%s", job_id, task_type)
