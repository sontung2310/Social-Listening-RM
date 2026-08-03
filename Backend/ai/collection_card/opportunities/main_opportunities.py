from ai.collection_card import company_cards
from ai.collection_card.opportunities import generate_action_items
from datetime import datetime


def run(history_id: str, company_id: str, limit: int = 10):
    """
    Generate opportunities from articles for a specific history_id and company.

    Args:
        history_id: History ID to fetch articles from
        company_id: Company ID from company_profiles
        limit: Number of top articles to analyze (default: 10)

    Returns:
        Dictionary with opportunities
    """
    try:
        if not history_id:
            raise ValueError("Please enter a valid history_id")
        if not company_id:
            raise ValueError("Please enter a valid company_id")

        print(f"[INFO] Generating opportunities for history: {history_id}")
        print(f"[INFO] Company: {company_id}")
        print(f"[INFO] Analyzing top {limit} articles...\n")

        # Generate opportunities from articles (returns simple list)
        opportunities_list = generate_action_items.generate_opportunities(
            history_id=history_id,
            company_id=company_id,
            limit=limit
        )

        # Print results
        generate_action_items.print_opportunities(opportunities_list)
        print("\n[INFO] Opportunity generation complete.")
        print(f"[INFO] Total opportunities found: {len(opportunities_list)}")
        print(opportunities_list)

        payload = {
            "history_id": history_id,
            "opportunities": opportunities_list,
            "total_opportunities": len(opportunities_list),
            "updated_at": datetime.now(),
            "next_refresh_at": None
        }

        success = company_cards.upsert_company_card(company_id, "opportunities", payload)

        if success:
            print(f"[SUCCESS] Opportunities saved to company card: {company_id}")
        else:
            print(f"[WARNING] Failed to save opportunities to company card")

        return opportunities_list
    except Exception as e:
        raise RuntimeError(f"run() failed: {e}")
        

# ----------- CLI for testing --------------------------------------
if __name__ == "__main__":
    # Example: Replace with actual history_id and company_id
    history_id = "68fdda1caf9de874acb5a32a"
    company_id = "690531c37c33c037fd2d9bda"
    result = run(history_id, company_id, limit=10)

