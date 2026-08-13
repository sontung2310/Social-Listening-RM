"""Helpers to write AI-enriched sample outputs for inspection."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional

from workers.queue import SAMPLE_OUTPUT_DIR

logger = logging.getLogger(__name__)


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.astimezone().isoformat().replace("+00:00", "Z") if obj.tzinfo else obj.isoformat() + "Z"
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def write_sample_output(sample_name: Optional[str], doc: Dict[str, Any]) -> Optional[Path]:
    """
    Write enriched AI document to sample_messages/output/<sample_name>.json
    so you can compare against sample_messages/input/.
    """
    if not sample_name:
        logger.warning("[Output] skip write — no sample_name on message")
        return None

    SAMPLE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = SAMPLE_OUTPUT_DIR / f"{sample_name}.json"
    path.write_text(
        json.dumps(_json_safe(doc), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("[Output] wrote AI result → %s", path)
    return path
