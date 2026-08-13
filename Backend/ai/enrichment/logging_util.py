"""Structured logging helpers for ai.enrichment."""
from __future__ import annotations

import logging
from typing import Any, Optional

LOGGER_NAME = "ai.enrichment"

logger = logging.getLogger(LOGGER_NAME)


def preview(text: Optional[str], limit: int = 160) -> str:
    flat = " ".join((text or "").split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1] + "…"


def log_step(event: str, **fields: Any) -> None:
    """Log a pipeline boundary event with key=value fields."""
    parts = [f"[{event}]"]
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={value!r}" if isinstance(value, str) else f"{key}={value}")
    logger.info(" ".join(parts))
