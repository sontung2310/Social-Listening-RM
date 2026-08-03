from ai.collection_card import company_cards
from ai.collection_card.ideas import generate_ideas
from datetime import datetime


def run(company_id: str, num_searches: int = 5, articles_per_search: int = 5):
    """
    Generate ideas from articles across recent searches.
    Does NOT require a history_id - analyzes the last N searches automatically.

    Args:
        company_id: Company ID from company_profiles
        num_searches: Number of recent searches to analyze (default: 10)
        articles_per_search: Number of top articles per search (default: 10)

    Returns:
        List of idea strings
    """
    try:
        if not company_id:
            raise ValueError("Please enter a valid company_id")

        print(f"[INFO] Generating ideas for company: {company_id}")
        print(f"[INFO] Analyzing last {num_searches} searches...")
        print(f"[INFO] Top {articles_per_search} articles per search...\n")

        # Generate ideas from recent searches (returns simple list)
        ideas_list = generate_ideas.generate_ideas(
            company_id=company_id,
            num_searches=num_searches,
            articles_per_search=articles_per_search
        )

        # Print results
        generate_ideas.print_ideas(ideas_list)
        print("\n[INFO] Idea generation complete.")
        print(f"[INFO] Total ideas generated: {len(ideas_list)}")
        print(ideas_list)

        # Save to MongoDB as a company card
        payload = {
            "ideas": ideas_list,
            "total_ideas": len(ideas_list),
            "num_searches_analyzed": num_searches,
            "articles_per_search": articles_per_search,
            "updated_at": datetime.now(),
            "next_refresh_at": None
        }

        success = company_cards.upsert_company_card(company_id, "ideas", payload)

        if success:
            print(f"[SUCCESS] Ideas saved to company card: {company_id}")
        else:
            print(f"[WARNING] Failed to save ideas to company card")

        return ideas_list
    except Exception as e:
        raise RuntimeError(f"run() failed: {e}")


# ----------- CLI for testing --------------------------------------
if __name__ == "__main__":
    # Example: Replace with actual company_id
    company_id = "690531c37c33c037fd2d9bda"
    result = run(company_id, num_searches=10, articles_per_search=10)
