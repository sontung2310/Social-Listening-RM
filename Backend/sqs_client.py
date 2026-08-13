"""Shared boto3 SQS client for Pace-Unit."""
from __future__ import annotations

from typing import Any

import boto3

import config


def sqs_client() -> Any:
    kwargs = {"region_name": config.AWS_REGION}
    if config.AWS_ACCESS_KEY_ID and config.AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = config.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = config.AWS_SECRET_ACCESS_KEY
    return boto3.client("sqs", **kwargs)
