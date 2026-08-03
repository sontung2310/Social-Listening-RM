from __future__ import annotations
import argparse
import json
from typing import List, Dict, Any, Set
from datetime import datetime, timezone

from ai.collection_card import company_cards
from ai.collection_card.new_competitors.fetch_context import (
    get_company_by_id,
    fetch_company_mentions_docs,
)
from ai.collection_card.new_competitors.extract_entities import extract_brand_candidates
from ai.collection_card.new_competitors.score_candidates import score_new_competitors
from ai.collection_card.new_competitors.lexicon import (
    AUTO_OEM_WHITELIST,
    AUTO_SUFFIX_HINTS,
    TICKER_WHITELIST,
)


def _existing_competitors(company_doc: dict) -> Set[str]:
    comps = company_doc.get("competitors") or []
    out: Set[str] = set()
    for c in comps:
        if isinstance(c, dict):
            name = (c.get("name") or "").strip()
            if name:
                out.add(name)
        elif isinstance(c, str):
            name = c.strip()
            if name:
                out.add(name)
    return out


def _looks_like_auto_brand(name: str, allow_tickers: bool = False) -> bool:
    # Remove generic industry clusters like "China-made EV"
    if " " in name and ("EV" in name or "ev" in name):
        if name not in AUTO_OEM_WHITELIST:
            return False

    # Known OEM list
    if name in AUTO_OEM_WHITELIST:
        return True

    # Tickers allowed only if flag enabled
    if name in TICKER_WHITELIST:
        return allow_tickers

    # Allow names ending in OEM-like suffix (Auto, Motors, Automotive…)
    for s in AUTO_SUFFIX_HINTS:
        if name.endswith(" " + s):
            return True

    return False


def run(
    company_id: str,
    *,
    limit_docs: int = 200,
    min_relevance: float = 0.20,
    days_back: int = 180,
    top_n: int = 12,
    persist: bool = True,
    verbose: bool = False,
) -> Dict[str, Any]:
    company = get_company_by_id(company_id)
    if not company:
        raise RuntimeError(f"Company not found: {company_id}")

    existing = _existing_competitors(company)

    docs, meta = fetch_company_mentions_docs(
        company_id,
        limit_docs=limit_docs,
        min_relevance=min_relevance,
        days_back=days_back,
    )

    if verbose:
        print(
            f" Strategy: {meta.get('strategy')}  Company: {meta.get('company_name') or '(unnamed)'}"
        )
        print(f" Fetched {len(docs)} documents (domain-filtered).")

    if not docs:
        payload = {
            "items": [],
            "updated_at": datetime.now(timezone.utc),
            "next_refresh_at": None,
            "meta": meta,
        }
        if persist:
            company_cards.upsert_company_card(company_id, "new_competitors", payload)
        # Build unified empty result
        result = {
            "existing_competitors": [{"name": n} for n in sorted(existing)],
            "new_competitors": [],
            "combined": sorted(existing),
        }
        return result

    # Extract candidates and remove the current company & known competitors
    texts = [
        " ".join(
            [d.get("ai_title", ""), d.get("ai_summary", ""), d.get("text", "")]
        ).strip()
        for d in docs
    ]
    exclude = set(existing)
    if meta.get("company_name"):
        exclude.add(meta["company_name"])

    freq_map = extract_brand_candidates(texts, exclude_names=exclude)

    if not freq_map:
        if verbose:
            print(" No brand-like co-mentions found after extraction.")
        payload = {
            "items": [],
            "updated_at": datetime.now(timezone.utc),
            "next_refresh_at": None,
            "meta": meta,
        }
        if persist:
            company_cards.upsert_company_card(company_id, "new_competitors", payload)

        result = {
            # "existing_competitors": [{"name": n} for n in sorted(existing)],
            # "new_competitors": [],
            "combined": sorted(existing),
        }
        return result

    ranked = score_new_competitors(docs, freq_map, top_n=top_n)

    # FINAL safety filter: only keep automotive-looking names
    allow_tickers = False  # set to True only if you want tickers to appear
    filtered = [
        r
        for r in ranked
        if _looks_like_auto_brand(r["name"], allow_tickers=allow_tickers)
        and r["name"] not in existing
        and r["name"] != meta.get("company_name")
    ]

    # Prepare new competitors list (already filtered as real OEM brands)
    new_competitors_output = [
        {
            "name": r["name"],
            "score": round(float(r.get("score", 0.0)), 4),
            "signals": r.get("signals", {}),
            "sample_urls": r.get("sample_urls", []),
        }
        for r in filtered
    ]

    # Existing competitors as a clean list of names
    existing_names = sorted(list(existing))

    # Build combined list (existing + new), dedup, preserve order (existing first)
    combined = list(
        dict.fromkeys(existing_names + [r["name"] for r in new_competitors_output])
    )

    # Persist to card if requested
    if persist:
        payload = {
            "items": combined,  # store the structured new items
            "updated_at": datetime.now(timezone.utc),
            "next_refresh_at": None,
            "meta": meta,
        }
        company_cards.upsert_company_card(company_id, "new_competitors", payload)
        if verbose:
            print(f" Stored {len(filtered)} new competitors in company card.")

    # Final structured result
    result = {
        # "existing_competitors": [{"name": n} for n in existing_names],
        # "new_competitors": new_competitors_output,
        "combined": combined,
        # "meta": meta,
    }
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Discover domain-precise new competitors.")
    p.add_argument("company_id", type=str)
    p.add_argument("--limit-docs", type=int, default=200)
    p.add_argument("--min-relevance", type=float, default=0.20)
    p.add_argument("--days-back", type=int, default=180)
    p.add_argument("--top-n", type=int, default=12)
    p.add_argument("--no-persist", action="store_true")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    out = run(
        args.company_id,
        limit_docs=args.limit_docs,
        min_relevance=args.min_relevance,
        days_back=args.days_back,
        top_n=args.top_n,
        persist=(not args.no_persist),
        verbose=args.verbose,
    )
    print(json.dumps(out, indent=2))
