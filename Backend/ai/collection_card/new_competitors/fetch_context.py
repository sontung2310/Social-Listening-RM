from __future__ import annotations
from typing import List, Dict, Any, Tuple, Set
from bson import ObjectId
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path
import os, re, time

# Load environment variables from ai.env
env_path = Path(__file__).parent.parent.parent / "AI.env"
load_dotenv(env_path)

from ai.collection_card.fetch_articles import get_company_articles
from ai.collection_card.new_competitors.domain import keywords_for

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI not found in AI.env")
client = MongoClient(MONGO_URI)
db = client["pace_database"]


# -------- basics --------
def get_company_by_id(company_id: str) -> dict | None:
    try:
        return db["company_profiles"].find_one({"_id": ObjectId(company_id)})
    except Exception:
        return None


def _ci_rx(s: str) -> re.Pattern:
    return re.compile(re.escape(s), re.IGNORECASE)


def _join_text(raw_id) -> str:
    if not raw_id:
        return ""
    raw = db["raw_insights"].find_one({"_id": raw_id}, {"text": 1})
    return (raw or {}).get("text", "") or ""


def _to_doc(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "url": r.get("url", "") or "",
        "ai_title": r.get("ai_title", "") or "",
        "ai_summary": r.get("ai_summary", "") or "",
        "text": _join_text(r.get("raw_id")),
        "source": r.get("source", "") or "",
        "published_ts": int(r.get("published_ts") or 0),
        "relevance_score": float(r.get("relevance_score", 0.0)),
        "tags": r.get("tags", []) or [],
    }


# -------- domain gating --------
def _domain_hit(s: str, domain_terms: Set[str]) -> bool:
    if not s:
        return False
    low = s.lower()
    return any(t in low for t in domain_terms)


def _is_automotive_doc(doc: Dict[str, Any], terms: Set[str]) -> bool:
    # Only keep docs that clearly talk automotive (title/summary/text/tags)
    if _domain_hit(doc.get("ai_title", ""), terms):
        return True
    if _domain_hit(doc.get("ai_summary", ""), terms):
        return True
    if _domain_hit(doc.get("text", ""), terms):
        return True
    tags = " ".join(doc.get("tags") or [])
    if _domain_hit(tags, terms):
        return True
    return False


def _filter_automotive_docs(
    docs: List[Dict[str, Any]], terms: Set[str]
) -> List[Dict[str, Any]]:
    return [d for d in docs if _is_automotive_doc(d, terms)]


# -------- strategies --------
def fetch_by_company_id(
    company_id: str, *, limit_docs: int, min_relevance: float
) -> List[Dict[str, Any]]:
    try:
        arts = get_company_articles(
            company_id, limit=limit_docs, min_relevance=min_relevance
        )
    except Exception:
        arts = []
    return [_to_doc(a) for a in arts or []]


def fetch_by_company_name(
    company_name: str, *, limit_docs: int, min_relevance: float, days_back: int
) -> List[Dict[str, Any]]:
    now = int(time.time())
    min_ts = now - days_back * 86400
    rx = _ci_rx(company_name)
    q = {
        "status": "done",
        "relevance_score": {"$gte": float(min_relevance)},
        "published_ts": {"$gte": min_ts},
        "$or": [{"ai_title": rx}, {"ai_summary": rx}],
    }
    proj = {
        "url": 1,
        "ai_title": 1,
        "ai_summary": 1,
        "raw_id": 1,
        "source": 1,
        "published_ts": 1,
        "relevance_score": 1,
        "tags": 1,
    }
    rows = list(
        db["ai_results"]
        .find(q, proj)
        .sort([("published_ts", -1), ("relevance_score", -1)])
        .limit(limit_docs)
    )
    return [_to_doc(r) for r in rows]


def fetch_by_sector_keywords(
    keywords: List[str], *, limit_docs: int, min_relevance: float, days_back: int
) -> List[Dict[str, Any]]:
    if not keywords:
        return []
    now = int(time.time())
    min_ts = now - days_back * 86400
    ors = []
    for kw in sorted(set(k.lower() for k in keywords if k and len(k) >= 3)):
        rx = re.compile(re.escape(kw), re.IGNORECASE)
        ors.append({"ai_title": rx})
        ors.append({"ai_summary": rx})
    if not ors:
        return []
    q = {
        "status": "done",
        "relevance_score": {"$gte": float(min_relevance)},
        "published_ts": {"$gte": min_ts},
        "$or": ors,
    }
    proj = {
        "url": 1,
        "ai_title": 1,
        "ai_summary": 1,
        "raw_id": 1,
        "source": 1,
        "published_ts": 1,
        "relevance_score": 1,
        "tags": 1,
    }
    rows = list(
        db["ai_results"]
        .find(q, proj)
        .sort([("published_ts", -1), ("relevance_score", -1)])
        .limit(limit_docs)
    )
    return [_to_doc(r) for r in rows]


# -------- unified --------
def fetch_company_mentions_docs(
    company_id: str,
    *,
    limit_docs: int = 200,
    min_relevance: float = 0.20,
    days_back: int = 180,
) -> Tuple[List[Dict[str, Any]], dict]:
    company = get_company_by_id(company_id) or {}
    company_name = (company.get("name") or "").strip()
    industry = (
        company.get("description") or company.get("industry") or ""
    ).strip() or "automotive"
    domain_terms = keywords_for(industry)  # <- domain keywords set

    # 1) exact company join
    docs = fetch_by_company_id(
        company_id, limit_docs=limit_docs, min_relevance=min_relevance
    )
    docs = _filter_automotive_docs(docs, domain_terms)
    if docs:
        return docs, {
            "strategy": "company_id+domain",
            "company_name": company_name,
            "industry": industry,
            "keywords_used": sorted(domain_terms),
        }

    # 2) co-mention by company name
    if company_name:
        docs = fetch_by_company_name(
            company_name,
            limit_docs=limit_docs,
            min_relevance=min_relevance,
            days_back=days_back,
        )
        docs = _filter_automotive_docs(docs, domain_terms)
        if docs:
            return docs, {
                "strategy": "co_name+domain",
                "company_name": company_name,
                "industry": industry,
                "keywords_used": sorted(domain_terms),
            }

    # 3) sector keywords (broad)
    docs = fetch_by_sector_keywords(
        sorted(domain_terms),
        limit_docs=limit_docs,
        min_relevance=min_relevance,
        days_back=days_back,
    )
    docs = _filter_automotive_docs(docs, domain_terms)
    return docs, {
        "strategy": "sector_keywords+domain",
        "company_name": company_name,
        "industry": industry,
        "keywords_used": sorted(domain_terms),
    }
