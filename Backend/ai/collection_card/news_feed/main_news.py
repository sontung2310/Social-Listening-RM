from ai.collection_card.news_feed import analyse_news_relevancy
from ai.collection_card import company_cards
from ai.collection_card import fetch_articles
from datetime import datetime

# def run(company_id: str):
def run(company_id: str,news_articles: dict[str,str]):
    try:
        if not news_articles:
            raise ValueError("No news articles retrieved")

        # Build company context
        context = fetch_articles.get_company_by_id(company_id)

        # Run AI relevance analysis
        analysis_result = analyse_news_relevancy.news_relevancy_rag(context, news_articles)
        
        # filter news
        filtered_news = [{
            "title": item["title"],
            "description": item["description"],
            "url": item["url"],
            "author": item["author"],
            "source": item["source"],
            "publishedAt": item["publishedAt"]
        }
        for item in analysis_result if item["relevance"] > 0.5
        ]
     
        # wrap and upsert into MongoDB
        payload = {
            "data": filtered_news,
            "updated_at": datetime.now(),
            "next_refresh_at": None
        }

        success = company_cards.upsert_company_card(company_id, "newsfeed", payload)

        # check for success
        if not success:
          
          raise RuntimeError("Failed to upsert news_feed card")
        

    except Exception as e:
        raise RuntimeError(f"run() failed: {e}")

# ----------- CLI for testing --------------------------------------
if __name__ == "__main__":
    company_id = "690531c37c33c037fd2d9bda"  # Example company ID
    news_artcles = [{"title": "Example 1",
                    "description" : "Example",
                    "url": "example.com",
                    "author" : "example",
                    "source" : "source.com",
                    "publishedAt" : "published"},

                    {"title": "Example 2",
                     "description" : "Example",
                        "url": "example.com",
                        "author" : "example",
                        "source" : "source.com",
                        "publishedAt" : "published"}]
    result = run(company_id, news_artcles)

