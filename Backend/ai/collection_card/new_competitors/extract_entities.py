from __future__ import annotations
from typing import Dict, Iterable, Set
import re
from .lexicon import AUTO_OEM_WHITELIST, AUTO_SUFFIX_HINTS, TICKER_WHITELIST

# Block obvious junk
STOP_EXACT: Set[str] = {
    "The",
    "US",
    "Here",
    "Key",
    "Earnings",
    "Strong",
    "Q3",
    "Dow",
    "Energy",
    "Alphabet",
    "Finance",
    "Today",
    "Update",
    "News",
    "Market",
    "Thread",
    "Official",
    "RSS",
    "Press",
    "Release",
}

# 1–3 Proper-Noun words; keep hyphens/& (e.g., “Mercedes-Benz”, “Lynk & Co”)
PHRASE_RX = re.compile(
    r"\b([A-Z][A-Za-z0-9&\-]+(?:\s+(?:&\s+)?[A-Z][A-Za-z0-9&\-]+){0,2})\b"
)
TICKER_RX = re.compile(r"\b[A-Z]{2,6}\b")


def _clean(p: str) -> str:
    return re.sub(r"\s+", " ", p.strip(" -")).strip()


def _has_auto_hint(name: str) -> bool:
    for s in AUTO_SUFFIX_HINTS:
        if name.endswith(" " + s) or name == s:
            return True
    return False


def _is_valid_phrase(p: str) -> bool:
    if not p or p in STOP_EXACT:
        return False
    # ban 1-word generic capitalized like “The”, “US” (already in STOP_EXACT),
    # but allow single words if they are whitelisted OEMs (e.g., Toyota, Rivian)
    words = p.split()
    if len(words) == 1 and p not in AUTO_OEM_WHITELIST:
        return False
    # If two/three words, require either whitelist OR brand-looking suffix
    if p in AUTO_OEM_WHITELIST:
        return True
    return _has_auto_hint(p)


def extract_brand_candidates(
    texts: Iterable[str], *, exclude_names: Set[str] | None = None
) -> Dict[str, int]:
    """
    Extract brand-like candidates; returns {name: frequency}.
    Only returns:
      - names in AUTO_OEM_WHITELIST, or
      - names ending with a brand-y suffix (Motors/Auto/Automotive/Mobility/Cars/Vehicles/EV/Truck…),
      - tickers present in TICKER_WHITELIST.
    """
    exclude = {e.strip() for e in (exclude_names or set()) if e}
    counts: Dict[str, int] = {}

    for t in texts:
        if not t:
            continue

        # Phrases (Proper Nouns)
        for m in PHRASE_RX.finditer(t):
            cand = _clean(m.group(1))
            if not cand or cand in exclude:
                continue
            if _is_valid_phrase(cand):
                counts[cand] = counts.get(cand, 0) + 1

        # Tickers (only whitelisted)
        for m in TICKER_RX.finditer(t):
            tk = m.group(0)
            if tk in exclude:
                continue
            if tk in TICKER_WHITELIST:
                counts[tk] = counts.get(tk, 0) + 1

    return counts
