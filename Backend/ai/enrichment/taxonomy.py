"""Fixed topic taxonomy for enrichment (v1 short list)."""
from __future__ import annotations

from typing import Dict, List

TOPIC_LABELS: List[str] = [
    "News",
    "Technology",
    "Marketing",
    "Business",
    "Product",
    "Other",
]

TOPIC_DESCRIPTIONS: Dict[str, str] = {
    "News": "Current events, press-style announcements, world/industry headlines",
    "Technology": "Software, AI, engineering, tools, technical how-tos",
    "Marketing": "Campaigns, ads, branding, growth, content/social marketing",
    "Business": (
        "Company ops, finance, hiring, competitors, pricing, partnerships, "
        "regulation as commercial context"
    ),
    "Product": (
        "Features, UX, releases, roadmaps, product feedback / support about "
        "the product itself"
    ),
    "Other": "Does not fit the five above with reasonable confidence",
}

TOPIC_SET = frozenset(TOPIC_LABELS)

SENTIMENT_LABELS = frozenset({"positive", "neutral", "negative"})

PROMPT_VERSION = "classify_v1.2+extract_v1.3"


def taxonomy_prompt_block() -> str:
    lines = [f"- {label}: {TOPIC_DESCRIPTIONS[label]}" for label in TOPIC_LABELS]
    return "\n".join(lines)
