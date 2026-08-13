"""Chunk split / merge for long-document enrichment."""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Sequence


def split_chunks(text: str, chunk_size: int = 1500, overlap: int = 100) -> List[str]:
    """Split text into overlapping character chunks."""
    text = text or ""
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append(text[start:end])
        if end >= n:
            break
        start = max(0, end - overlap)
    return chunks


def majority_topic(topics: Sequence[str], default: str = "Other") -> str:
    cleaned = [t for t in topics if t]
    if not cleaned:
        return default
    return Counter(cleaned).most_common(1)[0][0]


def mean_sentiment(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Average compound-like scores; pick dominant label by score sum."""
    if not results:
        return {"label": "neutral", "score": 0.0}
    labels: Counter = Counter()
    scores: List[float] = []
    for r in results:
        label = (r.get("label") or "neutral").lower()
        labels[label] += 1
        try:
            scores.append(float(r.get("score") or 0.0))
        except (TypeError, ValueError):
            scores.append(0.0)
    label = labels.most_common(1)[0][0]
    avg = sum(scores) / len(scores) if scores else 0.0
    return {"label": label, "score": round(avg, 4)}


def merge_keywords(
    keyword_lists: Sequence[Sequence[Dict[str, Any]]],
    top_n: int = 12,
) -> List[Dict[str, Any]]:
    """Merge keyword lists; keep max score per normalized term."""
    best: Dict[str, float] = {}
    display: Dict[str, str] = {}
    for kw_list in keyword_lists:
        for item in kw_list or []:
            term = (item.get("term") or "").strip()
            if not term:
                continue
            key = term.lower()
            try:
                score = float(item.get("score") or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            if key not in best or score > best[key]:
                best[key] = score
                display[key] = term.lower()
    ranked = sorted(best.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [{"term": display[k], "score": round(s, 4)} for k, s in ranked]


def reduce_summaries(summaries: Sequence[str], max_sentences: int = 2) -> str:
    """Join non-empty chunk summaries and trim to max_sentences."""
    parts = [s.strip() for s in summaries if (s or "").strip()]
    if not parts:
        return ""
    combined = " ".join(parts)
    # rough sentence split
    import re

    sents = [p.strip() for p in re.split(r"(?<=[.!?])\s+", combined) if p.strip()]
    return " ".join(sents[:max_sentences]) if sents else combined[:500]
