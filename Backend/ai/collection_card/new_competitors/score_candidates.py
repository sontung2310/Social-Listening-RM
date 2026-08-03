from __future__ import annotations
from typing import Dict, List, Any
import math, re

# Boost sources that are credible for industry signals
SOURCE_WEIGHT = {
    "newsapi": 1.0,
    "news_rss": 0.9,
    "bloomberg": 1.1,
    "reuters": 1.1,
    "yahoo": 0.9,
    "reddit_official": 0.5,
    "reddit_rss": 0.4,
    "twitter": 0.6,
    "x.com": 0.6,
}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _near_domain(text: str, domain_terms: set[str], win: int = 80) -> int:
    """
    Count how many domain terms appear within a local window around the candidate.
    We’ll search globally; a rough but effective alignment signal.
    """
    if not text:
        return 0
    low = text.lower()
    hits = 0
    for term in domain_terms:
        if term in low:
            hits += low.count(term)
    return hits


def score_new_competitors(
    docs: List[Dict[str, Any]],
    freq_map: Dict[str, int],
    top_n: int = 12,
    *,
    domain_terms: set[str] | None = None,
) -> List[Dict[str, Any]]:
    # precompute per-candidate signals
    domain_terms = domain_terms or set()

    results: List[Dict[str, Any]] = []

    # Build quick indices for sample URLs and per-candidate alignment
    fulltexts = [
        " ".join([d.get("ai_title", ""), d.get("ai_summary", ""), d.get("text", "")])
        for d in docs
    ]

    for cand, mentions in freq_map.items():
        # aggregate relevance & recency & sources
        rels, recency, srcs, urls = [], [], set(), []
        domain_hits = 0

        for d in docs:
            blob = " ".join(
                [d.get("ai_title", ""), d.get("ai_summary", ""), d.get("text", "")]
            )
            if cand in blob:
                rels.append(float(d.get("relevance_score", 0.0)))
                # crude recency (normalize later): newer published_ts → higher
                recency.append(float(d.get("published_ts", 0)))
                srcs.add((d.get("source") or "").lower())
                if len(urls) < 5:
                    urls.append(d.get("url", ""))
                # domain alignment
                if domain_terms:
                    domain_hits += _near_domain(blob, domain_terms)

        if not rels:
            continue

        avg_rel = sum(rels) / max(1, len(rels))
        # normalize recency by max
        max_ts = max(recency) if recency else 0.0
        min_ts = min(recency) if recency else 0.0
        avg_ts = sum(recency) / max(1, len(recency))
        recency_norm = (
            0.0 if max_ts == min_ts else (avg_ts - min_ts) / (max_ts - min_ts)
        )

        # source weight
        src_weight = 0.0
        for s in srcs:
            base = 0.7  # default
            for k, v in SOURCE_WEIGHT.items():
                if k in s:
                    base = max(base, v)
            src_weight += base
        src_weight = src_weight / max(1, len(srcs))

        # domain alignment: require some evidence; else downweight heavily
        align = _sigmoid(0.6 * domain_hits)  # grows with hits but saturates

        # final score
        score = (
            0.40 * _sigmoid(3.0 * (avg_rel - 0.4))
            + 0.20 * _sigmoid(3.0 * (mentions - 1.0))
            + 0.20 * recency_norm
            + 0.15 * src_weight
            + 0.25 * align
        )

        results.append(
            {
                "name": cand,
                "score": round(float(score), 4),
                "signals": {
                    "mentions": int(mentions),
                    "avg_relevance": round(float(avg_rel), 3),
                    "avg_recency": round(float(recency_norm), 3),
                    "sources": sorted(list(srcs)),
                    "domain_hits": int(domain_hits),
                },
                "sample_urls": urls,
            }
        )

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]
