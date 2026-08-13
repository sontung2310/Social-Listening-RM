"""Lightweight text cleaning for enrichment."""
from __future__ import annotations

import html
import re
from typing import Tuple

_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_WS_RE = re.compile(r"\s+")


def clean_text(text: str) -> Tuple[str, int, int]:
    """
    Strip HTML, URLs, emails; normalize whitespace.
    Returns (cleaned, chars_in, chars_out).
    """
    raw = text or ""
    chars_in = len(raw)
    out = html.unescape(raw)
    out = _TAG_RE.sub(" ", out)
    out = _URL_RE.sub(" ", out)
    out = _EMAIL_RE.sub(" ", out)
    out = _WS_RE.sub(" ", out).strip()
    return out, chars_in, len(out)


def head_tail_cap(text: str, max_chars: int = 6000) -> str:
    """Keep head+tail when text exceeds max_chars (for LLM context)."""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n...\n" + text[-half:]
