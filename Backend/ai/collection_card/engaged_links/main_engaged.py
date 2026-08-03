from __future__ import annotations
import argparse
import json
from typing import List, Dict, Any
from datetime import datetime, timezone

from ai.collection_card.company_cards import upsert_company_card
from ai.collection_card.engaged_links.fetch_engaged import collect_company_engagement


def _save_to_company_card(
    company_id: str, items: List[Dict], meta: Dict, verbose: bool = False
) -> bool:
    """Helper function to save engaged links data to MongoDB"""
    try:
        # keep full items server-side if you still want them for debugging/analysis
        urls = [i.get("url", "").strip() for i in items if i.get("url")]

        payload = {
            # "items": items,           # optional: remove if you NEVER need details
            "urls": urls,  # <- use this on the frontend
            "updated_at": datetime.now(timezone.utc),
            "next_refresh_at": None,
            "meta": meta,
        }

        success = upsert_company_card(company_id, "engaged_links", payload)

        if verbose:
            if success:
                print(
                    f"[SUCCESS] {len(items)} engaged links saved to company card: {company_id}"
                )
            else:
                print(f"[WARNING] Failed to save engaged links to company card")

        return success
    except Exception as e:
        if verbose:
            print(f"[ERROR] Failed to save to company card: {e}")
        return False


def run(
    company_id: str,
    *,
    top_n: int = 20,
    limit_docs: int = 400,
    min_relevance: float = 0.10,
    days_back: int = 200,
    persist: bool = True,
    verbose: bool = False,
) -> List[str]:
    """
    Compute the most engaged links for a company and (optionally) persist to the 'engaged_links' card.

    Args:
        company_id: Company ID from company_profiles
        top_n: Number of top links to return
        limit_docs: Number of documents to analyze
        min_relevance: Minimum relevance score for documents
        days_back: Number of days to look back
        persist: Whether to save to MongoDB
        verbose: Whether to print progress info

    Returns:
        List of top 10 URLs
    """
    try:
        if not company_id:
            raise ValueError("Please enter a valid company_id")

        if verbose:
            print(f"[INFO] Collecting engaged links for company: {company_id}")

        items, meta = collect_company_engagement(
            company_id,
            limit_docs=limit_docs,
            min_relevance=min_relevance,
            days_back=days_back,
        )

        if verbose:
            cname = meta.get("company_name") or "(unnamed)"
            print(f"[INFO] Strategy: {meta.get('strategy')}  Company: {cname}")
            print(
                f"[INFO] Collected {len(items)} company-related docs with engagement metrics."
            )

        # Return empty list if no items found
        if not items:
            if verbose:
                print("[INFO] No engaged links found for analysis.")

            # Save empty result to company card
            if persist:
                _save_to_company_card(company_id, [], meta, verbose)

            return []

        # Rank: engagement_score desc, then recency desc
        items.sort(
            key=lambda x: (
                float(x.get("engagement_score", 0.0)),
                int(x.get("published_ts", 0)),
            ),
            reverse=True,
        )
        top_items = items[:top_n]

        # Save structured data to MongoDB if requested
        if persist:
            _save_to_company_card(company_id, top_items, meta, verbose)

        # Extract URLs and return top 10
        urls = [item.get("url", "").strip() for item in items if item.get("url")]
        top_10_urls = urls[:10]

        if verbose:
            print(f"[INFO] Total engaged links found: {len(urls)}")
            print(f"[INFO] Returning top {len(top_10_urls)} URLs")

        return top_10_urls

    except Exception as e:
        raise RuntimeError(f"run() failed: {e}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Build 'engaged_links' card with most engaged company-related URLs."
    )
    p.add_argument("company_id", type=str)
    p.add_argument("--top-n", type=int, default=20)
    p.add_argument("--limit-docs", type=int, default=400)
    p.add_argument("--min-relevance", type=float, default=0.10)
    p.add_argument("--days-back", type=int, default=365)
    p.add_argument("--no-persist", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument(
        "--format",
        choices=["lines", "json"],
        default="lines",
        help="Output only URLs (one-per-line) or as a JSON array.",
    )

    args = p.parse_args()

    try:
        # Run the analysis
        top_urls = run(
            args.company_id,
            top_n=args.top_n,
            limit_docs=args.limit_docs,
            min_relevance=args.min_relevance,
            days_back=args.days_back,
            persist=(not args.no_persist),
            verbose=args.verbose,
        )

        # Output based on format
        if args.format == "json":
            print(json.dumps(top_urls, indent=2))
        else:  # lines format (default)
            for url in top_urls:
                print(url)

    except Exception as e:
        print(f"Error: {e}")
        exit(1)
