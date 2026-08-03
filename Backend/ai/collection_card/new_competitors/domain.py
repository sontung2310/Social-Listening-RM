from __future__ import annotations
from typing import Set, Dict

# Map company_profiles.industry → domain keywords
# You can extend these anytime.
INDUSTRY_KEYWORDS: Dict[str, Set[str]] = {
    "automotive": {
        "automotive",
        "automobile",
        "automobiles",
        "auto",
        "car",
        "cars",
        "vehicle",
        "vehicles",
        "electric vehicle",
        "ev",
        "evs",
        "hybrid",
        "phev",
        "bev",
        "suv",
        "sedan",
        "pickup",
        "truck",
        "cybertruck",
        "roadster",
        "gigafactory",
        "battery",
        "batteries",
        "charging",
        "charger",
        "supercharger",
        "autopilot",
        "self-driving",
        "autonomous",
        "drive unit",
        "drivetrain",
        "powertrain",
        "manufacturing",
        "production",
        "factory",
        "plant",
        "oem",
        "tier 1",
        "tier-1",
        "tier1",
        "supplier",
        "mobility",
        "fleet",
    },
    # sensible default fallbacks
    "ev": {
        "ev",
        "evs",
        "electric vehicle",
        "battery",
        "batteries",
        "charging",
        "charger",
        "autonomous",
        "self-driving",
        "mobility",
        "oem",
        "supplier",
    },
}


def keywords_for(industry: str | None) -> Set[str]:
    ind = (industry or "").strip().lower()
    if not ind:
        return INDUSTRY_KEYWORDS["ev"]  # conservative default for EV-ish
    if ind in INDUSTRY_KEYWORDS:
        return INDUSTRY_KEYWORDS[ind]
    # fuzzy: if industry mentions 'auto'
    if "auto" in ind:
        return INDUSTRY_KEYWORDS["automotive"]
    return INDUSTRY_KEYWORDS["ev"]
