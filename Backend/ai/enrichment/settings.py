"""NLP enrichment settings — change models / knobs here (not AI.env).

Credentials (API keys) stay in ``ai/AI.env``. Eval scripts may still override
these via environment variables for one-off experiments.
"""
from __future__ import annotations

import os
from typing import Any

# ---------------------------------------------------------------------------
# Models — switch here when moving to paid OpenRouter or a better OpenAI tier
# ---------------------------------------------------------------------------
# Current: OpenAI gpt-5-nano only (cost / accuracy / speed balance).
NLP_OPENAI_ONLY = True
NLP_PREFER_OPENAI_PRIMARY = True

# Used when OpenRouter is enabled (set NLP_OPENAI_ONLY=False).
NLP_PRIMARY_MODEL = "openrouter/free"

# OpenAI model used for production enrichment (and as backup when OpenRouter is on).
NLP_BACKUP_MODEL = "gpt-5-nano"

# Eval / guidance only — not used in the worker path.
NLP_JUDGE_MODEL = "gpt-5.6-luna"

# ---------------------------------------------------------------------------
# Pipeline knobs
# ---------------------------------------------------------------------------
NLP_TIMEOUT_MS = 3500
# Mid-length posts (~200–400 chars) still need summaries for Luna/word-cloud quality.
NLP_SUMMARY_MIN_CHARS = 220
NLP_LONG_CHARS = 4000


def _env_override(name: str, default: Any) -> Any:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    if isinstance(default, bool):
        return raw.strip().lower() in {"1", "true", "yes"}
    if isinstance(default, int):
        try:
            return int(raw)
        except ValueError:
            return default
    if isinstance(default, float):
        try:
            return float(raw)
        except ValueError:
            return default
    return raw


def get_openai_only() -> bool:
    return bool(_env_override("NLP_OPENAI_ONLY", NLP_OPENAI_ONLY))


def get_prefer_openai_primary() -> bool:
    return bool(_env_override("NLP_PREFER_OPENAI_PRIMARY", NLP_PREFER_OPENAI_PRIMARY))


def get_primary_model() -> str:
    return str(_env_override("NLP_PRIMARY_MODEL", NLP_PRIMARY_MODEL))


def get_backup_model() -> str:
    return str(_env_override("NLP_BACKUP_MODEL", NLP_BACKUP_MODEL))


def get_judge_model() -> str:
    return str(_env_override("NLP_JUDGE_MODEL", NLP_JUDGE_MODEL))


def get_timeout_ms() -> int:
    return int(_env_override("NLP_TIMEOUT_MS", NLP_TIMEOUT_MS))


def get_summary_min_chars() -> int:
    return int(_env_override("NLP_SUMMARY_MIN_CHARS", NLP_SUMMARY_MIN_CHARS))


def get_long_chars() -> int:
    return int(_env_override("NLP_LONG_CHARS", NLP_LONG_CHARS))
