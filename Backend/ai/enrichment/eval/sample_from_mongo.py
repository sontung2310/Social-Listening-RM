"""Stratified sampler from pace_database.raw_posts / raw_comments."""
from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai.enrichment")

POST_QUOTAS = {
    "x_playwright": 20,
    "reddit_playwright": 20,
    "youtube_search": 20,
    "reddit_rss": 7,
    "news_rss": 7,
    "newsapi": 7,
    "duckduckgo_web": 7,
    "guardian_api": 6,
    "hackernews_api": 6,
}

COMMENT_QUOTAS = {
    "x_playwright_comments": 35,
    "reddit_playwright_comments": 35,
    "youtube": 30,
}

EXCLUDE_SOURCES = frozenset({"smoke_test"})


def _mongo_db():
    """Prefer app config; fall back to AI.env MONGO_URI + pace_database."""
    try:
        from db.persist import get_mongo_db

        return get_mongo_db()
    except Exception:
        pass
    from pathlib import Path as P

    from dotenv import load_dotenv
    import os
    from pymongo import MongoClient
    from pymongo.server_api import ServerApi
    import certifi

    load_dotenv(P(__file__).resolve().parents[2] / "AI.env")
    uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGO_URI / MONGODB_URI not set")
    client = MongoClient(
        uri,
        server_api=ServerApi("1"),
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=15000,
    )
    dbname = os.getenv("MONGODB_DBNAME") or "pace_database"
    return client[dbname]


def _extract_post_text(doc: Dict[str, Any]) -> str:
    text = (doc.get("text") or "").strip()
    if text:
        return text
    title = (doc.get("title") or "").strip()
    if title:
        return title
    payload = doc.get("payload") or {}
    if isinstance(payload, dict):
        text = (payload.get("text") or "").strip()
        if text:
            return text
        return (payload.get("title") or "").strip()
    return ""


def _extract_comment_text(doc: Dict[str, Any]) -> str:
    text = (doc.get("text") or "").strip()
    if text:
        return text
    payload = doc.get("payload") or {}
    if isinstance(payload, dict):
        return (payload.get("text") or "").strip()
    return ""


def _length_bucket(n: int) -> str:
    if n < 200:
        return "short"
    if n >= 4000:
        return "long"
    return "medium"


def _sample_source(
    coll,
    source: str,
    need: int,
    *,
    content_type: str,
    text_fn,
    rng: random.Random,
) -> List[Dict[str, Any]]:
    if need <= 0:
        return []
    cursor = coll.find({"source": source})
    candidates: List[Dict[str, Any]] = []
    for doc in cursor:
        if doc.get("source") in EXCLUDE_SOURCES:
            continue
        text = text_fn(doc)
        if len(text.strip()) < 5:
            continue
        candidates.append(
            {
                "id": str(doc.get("_id")),
                "source": source,
                "external_id": doc.get("external_id") or doc.get("post_id") or doc.get("comment_id") or "",
                "content_type": content_type,
                "text": text,
                "text_chars": len(text),
                "length_bucket": _length_bucket(len(text)),
            }
        )
    if not candidates:
        logger.warning("[SAMPLE] source=%s need=%s found=0", source, need)
        return []

    # light length stratification
    by_bucket: Dict[str, List[Dict[str, Any]]] = {"short": [], "medium": [], "long": []}
    for c in candidates:
        by_bucket[c["length_bucket"]].append(c)
    for b in by_bucket:
        rng.shuffle(by_bucket[b])

    picked: List[Dict[str, Any]] = []
    # round-robin buckets
    buckets = ["short", "medium", "long"]
    while len(picked) < need and any(by_bucket[b] for b in buckets):
        for b in buckets:
            if len(picked) >= need:
                break
            if by_bucket[b]:
                picked.append(by_bucket[b].pop())
    logger.info(
        "[SAMPLE] source=%s need=%s got=%s pool=%s",
        source,
        need,
        len(picked),
        len(candidates),
    )
    return picked


def build_sample(
    *,
    seed: int = 42,
    post_quotas: Optional[Dict[str, int]] = None,
    comment_quotas: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    rng = random.Random(seed)
    db = _mongo_db()
    posts_coll = db["raw_posts"]
    comments_coll = db["raw_comments"]

    post_quotas = dict(post_quotas or POST_QUOTAS)
    comment_quotas = dict(comment_quotas or COMMENT_QUOTAS)

    posts: List[Dict[str, Any]] = []
    for source, need in post_quotas.items():
        posts.extend(
            _sample_source(
                posts_coll,
                source,
                need,
                content_type="post",
                text_fn=_extract_post_text,
                rng=rng,
            )
        )

    # top up posts to 100 from any remaining sources if short
    if len(posts) < 100:
        deficit = 100 - len(posts)
        used_ids = {p["id"] for p in posts}
        extras = []
        for doc in posts_coll.find({"source": {"$nin": list(EXCLUDE_SOURCES)}}).limit(500):
            sid = str(doc.get("_id"))
            if sid in used_ids:
                continue
            text = _extract_post_text(doc)
            if len(text) < 5:
                continue
            extras.append(
                {
                    "id": sid,
                    "source": doc.get("source"),
                    "external_id": doc.get("external_id") or "",
                    "content_type": "post",
                    "text": text,
                    "text_chars": len(text),
                    "length_bucket": _length_bucket(len(text)),
                }
            )
        rng.shuffle(extras)
        posts.extend(extras[:deficit])

    comments: List[Dict[str, Any]] = []
    for source, need in comment_quotas.items():
        comments.extend(
            _sample_source(
                comments_coll,
                source,
                need,
                content_type="comment",
                text_fn=_extract_comment_text,
                rng=rng,
            )
        )
    if len(comments) < 100:
        deficit = 100 - len(comments)
        used_ids = {c["id"] for c in comments}
        extras = []
        for doc in comments_coll.find({}).limit(800):
            sid = str(doc.get("_id"))
            if sid in used_ids:
                continue
            text = _extract_comment_text(doc)
            if len(text) < 5:
                continue
            extras.append(
                {
                    "id": sid,
                    "source": doc.get("source"),
                    "external_id": doc.get("external_id") or "",
                    "content_type": "comment",
                    "text": text,
                    "text_chars": len(text),
                    "length_bucket": _length_bucket(len(text)),
                }
            )
        rng.shuffle(extras)
        comments.extend(extras[:deficit])

    posts = posts[:100]
    comments = comments[:100]
    samples = posts + comments
    sources = sorted({s["source"] for s in samples if s.get("source")})
    return {
        "seed": seed,
        "n_posts": len(posts),
        "n_comments": len(comments),
        "n_total": len(samples),
        "sources": sources,
        "samples": samples,
    }


def save_fixture(payload: Dict[str, Any], path: Optional[Path] = None) -> Path:
    path = path or (
        Path(__file__).resolve().parent / "fixtures" / "mongo_sample_200.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[SAMPLE] wrote fixture path=%s n=%s", path, payload.get("n_total"))
    return path


def load_fixture(path: Optional[Path] = None) -> Dict[str, Any]:
    path = path or (
        Path(__file__).resolve().parent / "fixtures" / "mongo_sample_200.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    data = build_sample()
    out = save_fixture(data)
    print(f"saved {data['n_total']} samples → {out}")
    print("sources:", data["sources"])
