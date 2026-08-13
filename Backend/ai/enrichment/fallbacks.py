"""Tiny offline fallbacks when LLM providers fail."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List

_WORD = re.compile(r"[A-Za-z0-9]+")
_STOP = {
    "the", "a", "an", "and", "or", "but", "if", "then", "else", "when", "while",
    "is", "of", "to", "in", "for", "on", "by", "with", "as", "at", "from", "that",
    "this", "it", "its", "be", "are", "was", "were", "has", "had", "have", "not",
    "no", "we", "you", "they", "he", "she", "them", "his", "her", "their", "our",
    "i", "will", "would", "can", "could", "may", "might", "should", "also", "about",
    "into", "over", "under", "just", "like", "get", "got", "really", "very",
}


def fallback_sentiment(text: str) -> Dict[str, Any]:
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        scores = SentimentIntensityAnalyzer().polarity_scores(text or "")
        compound = float(scores.get("compound") or 0.0)
        if compound >= 0.05:
            label = "positive"
        elif compound <= -0.05:
            label = "negative"
        else:
            label = "neutral"
        return {
            "label": label,
            "score": round(abs(compound), 4),
            "compound_score": compound,
            "positive_score": float(scores.get("pos") or 0.0),
            "negative_score": float(scores.get("neg") or 0.0),
            "neutral_score": float(scores.get("neu") or 0.0),
        }
    except Exception:
        return {"label": "neutral", "score": 0.0}


def fallback_keywords(text: str, top_n: int = 8) -> List[Dict[str, Any]]:
    toks = [t.lower() for t in _WORD.findall(text or "") if t]
    toks = [t for t in toks if t not in _STOP and len(t) > 2]
    if not toks:
        return []
    freq = Counter(toks)
    total = sum(freq.values()) or 1
    return [
        {"term": w, "score": round(c / total, 4)}
        for w, c in freq.most_common(top_n)
    ]


def fallback_summary(text: str) -> str:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text or "") if p.strip()]
    if parts:
        return " ".join(parts[:2])
    return (text or "")[:300]


def build_fallback_result(text: str, *, allow_summary: bool) -> Dict[str, Any]:
    sentiment = fallback_sentiment(text)
    return {
        "sentiment": {
            "label": sentiment.get("label", "neutral"),
            "score": float(sentiment.get("score") or 0.0),
            "compound_score": sentiment.get("compound_score"),
            "positive_score": sentiment.get("positive_score"),
            "negative_score": sentiment.get("negative_score"),
            "neutral_score": sentiment.get("neutral_score"),
        },
        "topics": ["Other"],
        "topic_confidence": 0.0,
        "keywords": fallback_keywords(text),
        "summary": fallback_summary(text) if allow_summary else "",
        "entities": [],
        "validate_notes": ["fallback"],
    }
