from ai.collection_card.trending_topics import analyse_relevancy
from ai.collection_card import company_cards
from ai.collection_card import fetch_articles
from datetime import datetime

# def run(company_id: str):
def run(company_id: str,trending_topics: list):
    try:
        if not trending_topics:
            # trending_topics = ["Economics", "EVmotors", "GENzero", "AI advancements", "sustainability"]
            raise ValueError("No trending topics retrieved")

        # Build company context
        context = fetch_articles.get_company_by_id(company_id)

        # Run AI relevance analysis
        analysis_result = analyse_relevancy.relevancy_rag(context, trending_topics)

        print("Analysis Result:", analysis_result)

        # Filter topics with relevance > 0.5
        high_relevance_topics = [
            item["topic"]
            for item in analysis_result
                if isinstance(item, dict) and item.get("relevance", 0) > 0.5
            ]

        
        # wrap and upsert into MongoDB
        payload = {
            "data": high_relevance_topics,
            "updated_at": datetime.now(),
            "next_refresh_at": None
        }

        success = company_cards.upsert_company_card(company_id, "trending", payload)

        # check for success
        if not success:
            raise RuntimeError("Failed to upsert trending_topics card")
        

    except Exception as e:
        raise RuntimeError(f"run() failed: {e}")

# ----------- CLI for testing --------------------------------------
if __name__ == "__main__":
    company_id = "690531c37c33c037fd2d9bda"  # Example company ID
    result = run(company_id)

