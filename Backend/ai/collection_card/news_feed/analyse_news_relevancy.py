import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gpt
import json

import json
from math import ceil


def news_relevancy_rag(context: dict, news_articles: list[dict], batch_size: int = 25):
    company = context["name"]
    description = context["description"]
    competitors = ", ".join(context["competitors"])

    all_results = []

    # Split articles into batches
    num_batches = ceil(len(news_articles) / batch_size)

    for batch_index in range(num_batches):
        batch = news_articles[batch_index * batch_size : (batch_index + 1) * batch_size]

        # Format news articles for this batch
        articles_text = ""
        for idx, article in enumerate(batch):
            title = article.get("title", "Untitled")
            desc = article.get("description", "No description")
            source = article.get("source", "Unknown")
            articles_text += f"{idx + 1}. [{source}] {title}\n   {desc}\n\n"

        # Create the analysis prompt
        prompt = f"""
You are an AI market analyst. Your job is to assess which news articles are most relevant to {company}.

Company description:
{description}

Competitors:
{competitors}

News articles to evaluate:
{articles_text}

For each article, determine its relevance to {company} based on:
- Direct mentions of the company or its products/services
- Industry trends affecting the company
- Competitor activities
- Market conditions impacting the business
- Technology or regulatory changes relevant to operations

You MUST score STRICTLY. If a news is vague, random, unrelated to  the company's industry, or you cannot determine relevance from the company description, give it a LOW score (≤ 0.30).

Scoring rubric:
- 0.80 to 1.00 → very clearly about this company, its product space, its competitors, or a market force that directly affects it.
- 0.50 to 0.79 → possibly relevant but not certain, or only partially overlapping.
- 0.20 to 0.49 → weak / indirect relevance.
- 0.00 to 0.19 → unrelated, nonsense, too short, or insufficient information.

Important rules:
- Do NOT invent relevance.
- News that look like placeholders (e.g. "a", "b", "c", "test", "sample") MUST get ≤ 0.10.

Return ONLY a valid JSON array with NO additional text. Each article should have:
- "index": the article number (1-based)
- "relevance": score between 0.0 and 1.0
- "reasoning": brief explanation (1-2 sentences)

Format:
[
  {{"index": 1, "relevance": 0.95, "reasoning": "Direct mention of company's new product launch"}},
  {{"index": 2, "relevance": 0.45, "reasoning": "General industry trend with indirect impact"}}
]
"""

        try:
            # Run GPT/Groq call for this batch
            analysis = gpt.load_model(
                prompt, max_tokens=3000, temperature=0.2, stream=False
            )
            result = json.loads(analysis)

            if not isinstance(result, list):
                raise ValueError(f"Expected list, got {type(result)}")

            # Merge analysis with original article data
            for item in result:
                idx = item.get("index", 0) - 1
                if 0 <= idx < len(batch):
                    article = batch[idx].copy()
                    article["relevance"] = item.get("relevance", 0.0)
                    article["reasoning"] = item.get("reasoning", "")
                    all_results.append(article)

        except json.JSONDecodeError as e:
            print(f"JSON decoding failed for batch {batch_index + 1}: {e}")
            print(f"Raw response: {analysis}")
        except Exception as e:
            print(f"Error during batch {batch_index + 1}: {e}")

    # Sort all results by relevance
    all_results.sort(key=lambda x: x.get("relevance", 0), reverse=True)
    return all_results
