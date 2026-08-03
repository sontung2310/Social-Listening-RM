from __future__ import annotations
from typing import Dict, Any, List, Tuple
from datetime import datetime

# Reuse existing context fetcher already used by competitors module
from ai.collection_card.new_competitors.fetch_context import (
    get_company_by_id,
    fetch_company_mentions_docs,
)


def _pick_engagement_block(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a best-effort engagement dict from the document, trying many shapes.
    """
    # Direct common fields
    for k in ("engagement", "engagement_metrics", "stats", "metrics"):
        v = d.get(k)
        if isinstance(v, dict) and v:
            return v

    # Reddit-style fallbacks embedded in top-level
    # Common keys: score / ups / upvotes / num_comments / comments / upvote_ratio
    reddit_like = {}
    for k_src, k_dst in [
        ("score", "upvotes"),
        ("ups", "upvotes"),
        ("upvotes", "upvotes"),
        ("num_comments", "comments"),
        ("comments", "comments"),
        ("upvote_ratio", "upvote_ratio"),
    ]:
        if k_src in d and d.get(k_src) is not None:
            reddit_like[k_dst] = d.get(k_src)
    if reddit_like:
        return reddit_like

    # Nested meta.* shapes (e.g., meta.reddit, meta.engagement)
    meta = d.get("meta") or {}
    v = meta.get("engagement")
    if isinstance(v, dict) and v:
        return v
    reddit_meta = meta.get("reddit")
    if isinstance(reddit_meta, dict) and reddit_meta:
        # Normalize a few common keys
        norm = {}
        if "score" in reddit_meta:
            norm["upvotes"] = reddit_meta["score"]
        if "ups" in reddit_meta:
            norm["upvotes"] = reddit_meta["ups"]
        if "num_comments" in reddit_meta:
            norm["comments"] = reddit_meta["num_comments"]
        if "upvote_ratio" in reddit_meta:
            norm["upvote_ratio"] = reddit_meta["upvote_ratio"]
        if norm:
            return norm

    return {}


def _infer_proxy_engagement(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a proxy engagement when none is available:
      - For Reddit-like sources, try more field names.
      - For news articles, synthesize a 'views' proxy from relevance and recency.
    """
    src = (doc.get("source") or "").lower()
    eng = {}

    # Try more Reddit/HN-ish keys that might be present in odd places
    if "reddit" in src or "reddit" in (doc.get("url") or "").lower():
        for k_src, k_dst in [
            ("score", "upvotes"),
            ("ups", "upvotes"),
            ("points", "upvotes"),  # HN-like
            ("num_comments", "comments"),
            ("comments", "comments"),
        ]:
            if k_src in doc and doc.get(k_src) is not None:
                eng[k_dst] = doc.get(k_src)

        meta = doc.get("meta") or {}
        if isinstance(meta.get("reddit"), dict):
            r = meta["reddit"]
            if "score" in r and r["score"] is not None:
                eng["upvotes"] = r["score"]
            if "num_comments" in r and r["num_comments"] is not None:
                eng["comments"] = r["num_comments"]

    # If still empty (typical for newsapi/news_rss), synthesize a mild 'views' proxy
    if not eng:
        rel = float(doc.get("relevance", doc.get("relevance_score", 0.0)) or 0.0)
        ts = int(doc.get("published_ts") or 0)
        # recency factor in [0,1]: newer gets closer to 1 (30-day half-life)
        import time, math

        now = int(time.time())
        days = max(0.0, (now - ts) / 86400.0) if ts > 0 else 365.0
        recency = 1.0 / (1.0 + (days / 30.0))  # ~0.97 at 1 day, ~0.5 at 30 days
        # scale into a "views" proxy bucket (tunable constant)
        views_proxy = max(0.0, 1000.0 * (0.6 * rel + 0.4 * recency))
        eng = {"views": views_proxy, "proxy": True}

    return eng


def engagement_score(doc: Dict[str, Any]) -> float:
    """
    Composite engagement with Reddit priority.
    Base: likes + 2*comments + 3*shares + 1.5*upvotes + 0.5*log10(views+1)
    Reddit bonus: stronger weight to comments & upvotes + ratio factor.
    """
    eng = _pick_engagement_block(doc)
    if not eng:
        eng = _infer_proxy_engagement(doc)

    def f(x, d=0.0):
        try:
            return float(x)
        except Exception:
            return d

    likes = f(eng.get("likes", eng.get("reactions", 0)))
    com = f(eng.get("comments", eng.get("replies", 0)))
    shares = f(eng.get("shares", eng.get("retweets", 0)))
    ups = f(eng.get("upvotes", eng.get("score", 0)))
    views = f(eng.get("views", eng.get("impressions", 0)))
    ratio = f(eng.get("upvote_ratio", 0))  # Reddit-only field, 0..1

    import math

    view_term = 0.5 * math.log10(max(0.0, views) + 1.0)

    # Base score
    base = likes + 2.0 * com + 3.0 * shares + 1.5 * ups + view_term

    # Reddit priority: bigger emphasis on discussion & upvotes, plus ratio lift
    if _is_reddit(doc):
        # Tunables (can move to env if you like)
        import os

        REDDIT_COM_W = float(os.getenv("ENG_REDDIT_COM_W", 2.5))
        REDDIT_UP_W = float(os.getenv("ENG_REDDIT_UP_W", 2.0))
        RATIO_BONUS_W = float(os.getenv("ENG_RATIO_BONUS_W", 1.0))

        reddit_bonus = (
            (REDDIT_COM_W * com)
            + (REDDIT_UP_W * ups)
            + (RATIO_BONUS_W * ratio * (com + ups))
        )
        return base + reddit_bonus

    return base


def _to_float(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def collect_company_engagement(
    company_id: str,
    *,
    limit_docs: int = 300,
    min_relevance: float = 0.15,
    days_back: int = 180,
):
    docs, meta = fetch_company_mentions_docs(
        company_id,
        limit_docs=limit_docs,
        min_relevance=min_relevance,
        days_back=days_back,
    )

    enriched = []
    seen = set()
    for d in docs:
        url = (d.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)

        eng = _pick_engagement_block(d) or _infer_proxy_engagement(d)
        score = engagement_score(d)

        enriched.append(
            {
                "url": url,
                "title": d.get("ai_title") or d.get("title") or "",
                "summary": d.get("ai_summary") or d.get("summary") or "",
                "source": d.get("source") or "",
                "published_ts": int(d.get("published_ts") or 0),
                "relevance": float(
                    d.get("relevance", d.get("relevance_score", 0.0)) or 0.0
                ),
                "engagement": eng,
                "engagement_score": score,
                "is_reddit": _is_reddit(d),
            }
        )

    # Hard preference: Reddit before others at same score; then by score desc; then by recency
    enriched.sort(
        key=lambda r: (
            0 if r["relevance"] else 1,  # Reddit first
            -r["engagement_score"],  # higher engagement
            -(r["published_ts"] or 0),  # newer
            -r["is_reddit"],  # more relevant
        )
    )

    return enriched, meta


def _is_reddit(doc: Dict[str, Any]) -> bool:
    s = (doc.get("source") or "").lower()
    u = (doc.get("url") or "").lower()
    return ("reddit" in s) or ("reddit.com" in u)
