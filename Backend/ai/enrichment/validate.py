"""JSON repair, taxonomy clamp, keyword filtering, result merge."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from ai.enrichment.logging_util import log_step
from ai.enrichment.taxonomy import SENTIMENT_LABELS, TOPIC_SET

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_STOP = frozenset(
    {
        "the", "a", "an", "and", "or", "but", "if", "then", "else", "when", "while",
        "is", "of", "to", "in", "for", "on", "by", "with", "as", "at", "from", "that",
        "this", "it", "its", "be", "are", "was", "were", "has", "had", "have", "not",
        "no", "we", "you", "they", "he", "she", "them", "his", "her", "their", "our",
        "i", "will", "would", "can", "could", "may", "might", "should", "also", "about",
        "just", "like", "get", "got", "really", "very", "so", "too", "than", "into",
        "now", "soon", "gets", "around", "becoming", "share", "here", "there", "come",
        "coming", "going", "still", "even", "much", "many", "thing", "things", "stuff",
        "time", "finally", "quick", "without", "please", "thanks", "hello", "hi",
    }
)


def extract_json_object(raw: str) -> Optional[Dict[str, Any]]:
    """Parse JSON from model output; strip markdown fences; find first object."""
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            return None
    return None


def _clamp_float(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, v))


def validate_classify(obj: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[str]]:
    """Validate Call A output. Returns (normalized, repair_notes)."""
    notes: List[str] = []
    if not obj:
        notes.append("empty_classify")
        return {
            "sentiment": {"label": "neutral", "score": 0.0},
            "topic": "Other",
            "topic_confidence": 0.0,
        }, notes

    sent = obj.get("sentiment") if isinstance(obj.get("sentiment"), dict) else {}
    label = str(sent.get("label") or "neutral").strip().lower()
    if label not in SENTIMENT_LABELS:
        notes.append(f"sentiment_clamp:{label}")
        label = "neutral"
    score = _clamp_float(sent.get("score"), 0.0)

    topic = str(obj.get("topic") or "Other").strip()
    # normalize case to taxonomy
    topic_map = {t.lower(): t for t in TOPIC_SET}
    if topic in TOPIC_SET:
        pass
    elif topic.lower() in topic_map:
        notes.append(f"topic_case:{topic}")
        topic = topic_map[topic.lower()]
    else:
        notes.append(f"topic_clamp:{topic}")
        topic = "Other"

    conf = _clamp_float(obj.get("topic_confidence"), 0.0)
    return {
        "sentiment": {"label": label, "score": score},
        "topic": topic,
        "topic_confidence": conf,
    }, notes


def _term_in_text(term: str, text: str) -> bool:
    """Case-insensitive substring check with light normalization."""
    t = (term or "").strip().lower()
    if not t:
        return False
    hay = (text or "").lower()
    if t in hay:
        return True
    # allow hyphen/space variants
    alt = t.replace("-", " ")
    if alt != t and alt in hay:
        return True
    return False


def validate_extract(
    obj: Optional[Dict[str, Any]],
    source_text: str,
    *,
    allow_summary: bool,
) -> Tuple[Dict[str, Any], List[str]]:
    """Validate Call B output."""
    notes: List[str] = []
    if not obj:
        notes.append("empty_extract")
        return {"keywords": [], "summary": ""}, notes

    raw_kws = obj.get("keywords") or []
    if not isinstance(raw_kws, list):
        raw_kws = []
        notes.append("keywords_not_list")

    cleaned: List[Dict[str, Any]] = []
    seen = set()
    for item in raw_kws:
        if isinstance(item, str):
            term, score = item, 0.5
        elif isinstance(item, dict):
            term = str(item.get("term") or "").strip().lower()
            score = _clamp_float(item.get("score"), 0.5)
        else:
            continue
        term = re.sub(r"\s+", " ", term).strip()
        # Keep hashtag bodies without '#'; drop leading @.
        if term.startswith("#"):
            term = term.lstrip("#").strip()
        if term.startswith("@"):
            notes.append(f"kw_drop_handle:{term}")
            continue
        if not term or term in _STOP:
            notes.append(f"kw_drop_stop:{term}")
            continue
        # Drop obvious incomplete trailing prepositions/articles (fragment heuristic).
        tokens = term.split()
        if tokens and tokens[-1] in {
            "of", "in", "on", "to", "for", "with", "and", "or", "the", "a", "an",
            "is", "are", "be", "by", "at", "from", "as",
        }:
            notes.append(f"kw_drop_fragment:{term}")
            continue
        if len(tokens) > 3:
            term = " ".join(tokens[:3])
            notes.append("kw_trim_ngram")
        if term in seen:
            continue
        if not _term_in_text(term, source_text):
            # Allow hashtag body match when source still has '#term'
            if not _term_in_text("#" + term, source_text):
                notes.append(f"kw_not_in_text:{term}")
                continue
        seen.add(term)
        cleaned.append({"term": term, "score": score})

    cleaned = sorted(cleaned, key=lambda x: x["score"], reverse=True)[:12]

    summary = ""
    if allow_summary:
        summary = str(obj.get("summary") or "").strip()
    elif obj.get("summary"):
        notes.append("summary_forced_empty")
        summary = ""

    return {"keywords": cleaned, "summary": summary}, notes


def merge_enrichment(
    classify: Dict[str, Any],
    extract: Dict[str, Any],
    *,
    classify_notes: Optional[List[str]] = None,
    extract_notes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    notes = list(classify_notes or []) + list(extract_notes or [])
    if notes:
        log_step("VALIDATE", notes=";".join(notes[:20]), note_count=len(notes))
    sentiment = classify.get("sentiment") or {"label": "neutral", "score": 0.0}
    topic = classify.get("topic") or "Other"
    return {
        "sentiment": sentiment,
        "topics": [topic],
        "topic_confidence": float(classify.get("topic_confidence") or 0.0),
        "keywords": extract.get("keywords") or [],
        "summary": extract.get("summary") or "",
        "entities": [],
        "validate_notes": notes,
    }
