# AI/collection_card/opportunities/generate_action_items.py
"""
Generate actionable opportunities from articles for a specific history_id and company.
"""

from __future__ import annotations
import os
import sys
import json
import re
from typing import List, Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gpt

from ai.collection_card import fetch_articles
from ai.collection_card.opportunities import fetch_recent_articles


def _build_opportunities_prompt(
    company_name: str,
    company_description: str,
    competitors: List[str],
    articles: List[Dict[str, Any]]
) -> str:
    """
    Build a prompt to generate opportunities from articles.
    """
    comp_str = ", ".join([c for c in competitors or [] if c]) or "N/A"

    # Format articles for prompt
    article_lines = []
    for i, article in enumerate(articles, 1):
        sentiment = article.get("sentiment", "neutral")
        tags = ", ".join(article.get("tags", []))

        article_lines.append(
            f"{i}. [{article.get('source', 'Unknown')}] {article.get('ai_title', 'Untitled')}\n"
            f"   Summary: {article.get('ai_summary', 'No summary')}\n"
            f"   URL: {article.get('url', '')}\n"
            f"   Sentiment: {sentiment} | Relevance: {article.get('relevance_score', 0):.2f}\n"
            f"   Tags: {tags}"
        )

    articles_block = "\n\n".join(article_lines) if article_lines else "No articles available."

    return f"""
Act as a marketing strategists and cosultant who analyses content based on industry or products/services to ascertain 
relevance for potential reuse in marketing/content marketing, social media or thought leadership. 
For {company_name}, analyze these articles and identify OPPORTUNITIES.

Company Profile:
- Name: {company_name}
- Description: {company_description}
- Competitors: {comp_str}

Articles to Analyze:
{articles_block}

TASK:
Identify business opportunities from these articles. Each opportunity should be:
1. SPECIFIC - mention names, companies, technologies from articles
2. ACTIONABLE - something {company_name} can realistically pursue
3. VALUABLE - has clear business impact
4. RETURN - a minimum of 2 opportunities, maximum of 6 opportunities

OPPORTUNITY TYPES:
- **Content/Writing opportunities** - Topics to write about, blog posts, newsletters, emails, social media posts
- **Partnership opportunities** - Companies/people to collaborate with
- **Market opportunities** - New markets or customer segments to explore
- **Product opportunities** - Features, services, or products to develop
- **Competitive insights** - Competitor gaps or weaknesses to exploit
- **Trend opportunities** - Emerging trends to capitalize on

IMPORTANT: Return a MAXIMUM of 6 opportunities and a MINIMUM of 2 opportunities. Prioritize the most impactful ones.

OUTPUT FORMAT (JSON only, no markdown):
[
  {{
    "title": "Brief opportunity title",
    "description": "What is the opportunity (2-3 sentences)",
    "action_items": "Specific next steps to pursue this opportunity",
    "priority": "high" | "medium" | "low",
    "opportunity_type": "content" | "partnership" | "market" | "product" | "competitive" | "trend",
    "source_article": "Article title from list",
    "source_url": "Article URL"
  }}
]

Return empty array [] if no opportunities found.
""".strip()


def _extract_json(text: str) -> str:
    """Extract JSON array from GPT response."""
    if not text:
        return "[]"

    t = text.strip()

    # Remove markdown code fences
    if t.startswith("```json"):
        t = t[7:]
    if t.startswith("```"):
        t = t[3:]
    if t.endswith("```"):
        t = t[:-3]
    t = t.strip()

    # If already clean JSON
    if t.startswith("[") and t.endswith("]"):
        return t

    # Find first JSON array
    match = re.search(r'\[.*\]', t, re.DOTALL)
    return match.group(0) if match else "[]"


def _prioritize_opportunities(opportunities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort opportunities by priority."""
    priority_weight = {"high": 3, "medium": 2, "low": 1}

    def sort_key(opp):
        return priority_weight.get(opp.get("priority", "medium"), 2)

    return sorted(opportunities, key=sort_key, reverse=True)


def generate_opportunities(
    history_id: str,
    company_id: str,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Generate opportunities from articles for a specific history_id and company.

    Args:
        history_id: History ID to fetch articles from
        company_id: Company ID from company_profiles collection
        limit: Number of top articles to analyze (default: 10)

    Returns:
        Dictionary with company info and list of opportunities
    """

    # 1. Get company context
    company_context = fetch_articles.get_company_by_id(company_id)
    if not company_context:
        return {
            "error": f"Company not found: {company_id}",
            "opportunities": []
        }

    # 2. Fetch top articles by history_id
    articles = fetch_recent_articles.fetch_articles_by_history_id(
        history_id=history_id,
        limit=limit,
        include_sentiment=True
    )

    if not articles:
        return {
            "company": company_context,
            "message": f"No articles found for history_id: {history_id}",
            "opportunities": []
        }

    # 3. Build prompt and call GPT
    prompt = _build_opportunities_prompt(
        company_name=company_context["name"],
        company_description=company_context["description"],
        competitors=company_context["competitors"],
        articles=articles
    )

    raw_response = gpt.load_model(
        prompt,
        max_tokens=2500,
        temperature=0.3,
        stream=False
    )

    # 4. Parse JSON response
    json_str = _extract_json(raw_response)

    try:
        opportunities = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse GPT response: {e}")
        return {
            "company": company_context,
            "error": "Failed to parse GPT response",
            "opportunities": [],
            "raw_response": raw_response
        }

    if not isinstance(opportunities, list):
        opportunities = []

    # 5. Clean and normalize opportunities
    cleaned_opportunities = []
    for opp in opportunities:
        if not isinstance(opp, dict):
            continue

        cleaned_opportunities.append({
            "title": (opp.get("title") or "").strip(),
            "description": (opp.get("description") or "").strip(),
            "action_items": (opp.get("action_items") or "").strip(),
            "priority": opp.get("priority", "medium").lower(),
            "opportunity_type": opp.get("opportunity_type", "general").lower(),
            "source_article": (opp.get("source_article") or "").strip(),
            "source_url": (opp.get("source_url") or "").strip(),
        })

    # 6. Prioritize and limit to max 6 opportunities
    prioritized_opportunities = _prioritize_opportunities(cleaned_opportunities)

    # Enforce maximum of 6 opportunities
    MAX_OPPORTUNITIES = 6
    final_opportunities = prioritized_opportunities[:MAX_OPPORTUNITIES]

    # Convert to simple list format: just the opportunity titles
    opportunities_list = [opp["description"] for opp in final_opportunities]

    return opportunities_list


def print_opportunities(opportunities_list: List[str]):
    """Pretty print opportunities for CLI."""

    if not opportunities_list:
        print("[INFO] No opportunities found.")
        return

    print(f"\n{'='*80}")
    print(f"OPPORTUNITIES (Max 6)")
    print(f"{'='*80}")
    print(f"Found {len(opportunities_list)} opportunities:\n")

    for i, opp in enumerate(opportunities_list, 1):
        print(f"{i}. {opp}")

    print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate opportunities from articles")
    parser.add_argument("history_id", help="History ID to fetch articles from")
    parser.add_argument("company_id", help="Company ID from company_profiles")
    parser.add_argument("--limit", type=int, default=10, help="Number of articles to analyze")

    args = parser.parse_args()

    print(f"[INFO] Generating opportunities for history {args.history_id}...")
    result = generate_opportunities(args.history_id, args.company_id, limit=args.limit)
    print_opportunities(result)
