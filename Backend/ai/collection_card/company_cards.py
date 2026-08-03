# AI/shared/company_cards.py
from __future__ import annotations
from typing import Any, Dict, Optional, Iterable
from bson import ObjectId
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv
from pathlib import Path
import os

# Load environment variables from ai.env
env_path = Path(__file__).parent.parent / "AI.env"
load_dotenv(env_path)

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI not found in AI.env")
client = MongoClient(MONGO_URI)
db = client["pace_database"]

# Keep this in one place so FE/BE stay consistent
ALLOWED_CARD_NAMES: set[str] = {
    "new_competitors",
    "engaged_links",
    "ideas",
    "opportunities",
    "trending",
    "newsfeed",
}


def _normalize_card_name(card_name: str) -> Optional[str]:
    if not card_name:
        return None
    name = card_name.strip().lower()
    return name if name in ALLOWED_CARD_NAMES else None


def get_company_card(company_id: str, card_name: str) -> Optional[Dict[str, Any]]:
    """
    Read a stored card payload from company_profiles.cards[card_name].
    Returns None if company or card does not exist.
    """
    try:
        oid = ObjectId(company_id)
    except Exception:
        return None

    name = _normalize_card_name(card_name)
    if not name:
        return None

    doc = db.company_profiles.find_one({"_id": oid}, {"cards": 1})
    if not doc:
        return None

    cards = doc.get("cards") or {}
    return cards.get(name)


def upsert_company_card(
    company_id: str, card_name: str, payload: Dict[str, Any]
) -> bool:
    """
    Write/replace a card payload at company_profiles.cards[card_name].
    Returns True on success, False otherwise.
    """
    try:
        oid = ObjectId(company_id)
    except Exception:
        return False

    name = _normalize_card_name(card_name)
    if not name:
        return False

    res = db.company_profiles.update_one(
        {"_id": oid}, {"$set": {f"cards.{name}": payload}}
    )
    return bool(res.matched_count)


def bulk_upsert_company_cards(
    company_id: str, card_items: Iterable[tuple[str, Dict[str, Any]]]
) -> bool:
    """
    Bulk upsert multiple cards in one round trip:
      card_items = [("new_competitors", {...}), ("engaged_links", {...}), ...]
    """
    try:
        oid = ObjectId(company_id)
    except Exception:
        return False

    to_set: Dict[str, Any] = {}
    for name, payload in card_items:
        norm = _normalize_card_name(name)
        if norm:
            to_set[f"cards.{norm}"] = payload

    if not to_set:
        return False

    res = db.company_profiles.update_one({"_id": oid}, {"$set": to_set})
    return bool(res.matched_count)
