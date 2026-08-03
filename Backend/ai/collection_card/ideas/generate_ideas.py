# AI/collection_card/ideas/generate_ideas.py
"""
Generate innovative ideas from articles across multiple searches.
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
from ai.collection_card.ideas import fetch_searches


def _build_ideas_prompt(
    company_name: str,
    company_description: str,
    competitors: List[str],
    articles: List[Dict[str, Any]]
) -> str:
    """
    Build a prompt to generate innovative ideas from articles.
    """
    comp_str = ", ".join([c for c in competitors or [] if c]) or "N/A"

    # Format articles for prompt with full text
    article_lines = []
    for i, article in enumerate(articles, 1):
        sentiment = article.get("sentiment", "neutral")
        tags = ", ".join(article.get("tags", []))

        # Truncate text if too long (keep first 500 chars for context)
        full_text = article.get("text", "")
        truncated_text = full_text[:500] + "..." if len(full_text) > 500 else full_text

        article_lines.append(
            f"{i}. [{article.get('source', 'Unknown')}] {article.get('ai_title', 'Untitled')}\n"
            f"   Summary: {article.get('ai_summary', 'No summary')}\n"
            f"   Article Text: {truncated_text}\n"
            f"   URL: {article.get('url', '')}\n"
            f"   Sentiment: {sentiment} | Relevance: {article.get('relevance_score', 0):.2f}\n"
            f"   Tags: {tags}"
        )

    articles_block = "\n\n".join(article_lines) if article_lines else "No articles available."

    return f"""
You are an innovative business strategist for {company_name}. Analyze these industry articles and generate CREATIVE IDEAS.

Company Profile:
- Name: {company_name}
- Description: {company_description}
- Competitors: {comp_str}

Industry Articles to Analyze (from recent searches):
{articles_block}

TASK:
Generate innovative and actionable IDEAS that {company_name} can pursue based on trends and insights from these articles. Think broadly and creatively!

IDEA CATEGORIES:
- **Content Ideas** - Blog posts, newsletters, whitepapers, case studies, webinars, podcasts, videos
- **Product Ideas** - New features, services, tools, or products to develop
- **Marketing Ideas** - Campaigns, positioning strategies, channels to explore
- **Partnership Ideas** - Collaborations, integrations, co-marketing opportunities
- **Innovation Ideas** - Novel approaches, emerging tech adoption, process improvements
- **Community Ideas** - Events, forums, user groups, educational programs

REQUIREMENTS:
1. Each idea should be 2-3 lines long and DESCRIPTIVE
2. Ideas should be ACTIONABLE - something {company_name} can realistically execute
3. DO NOT reference specific articles or sources in the idea text
4. Mix different categories - don't focus on just one type
5. Be creative but practical based on the industry trends you see
6. Remove all the AI markers

IMPORTANT: Return a MINIMUM of 2 ideas and a MAXIMUM of 6 ideas.

OUTPUT FORMAT (JSON only, no markdown):
[
  {{
    "idea": "2-3 line descriptive idea that is self-contained and doesn't reference articles. Explain what the idea is, why it matters, and what action to take.",
    "category": "content" | "product" | "marketing" | "partnership" | "innovation" | "community"
  }}
]

Return at least 2 ideas, max 6 ideas. Each idea must be 2-3 lines, descriptive, and self-contained.
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


def _diversify_ideas(ideas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ensure diversity of categories while maintaining quality.
    Returns ideas with varied categories when possible.
    """
    if len(ideas) <= 2:
        return ideas

    # Group by category
    by_category = {}
    for idea in ideas:
        cat = idea.get("category", "general")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(idea)

    # Interleave categories to ensure diversity
    result = []
    categories = list(by_category.keys())
    idx = 0

    while len(result) < len(ideas):
        cat = categories[idx % len(categories)]
        if by_category[cat]:
            result.append(by_category[cat].pop(0))
        idx += 1

    return result


def generate_ideas(
    company_id: str,
    num_searches: int = 10,
    articles_per_search: int = 10
) -> List[str]:
    """
    Generate ideas from articles across recent searches.

    Args:
        company_id: Company ID from company_profiles collection
        num_searches: Number of recent searches to include (default: 10)
        articles_per_search: Number of top articles per search (default: 10)

    Returns:
        List of idea strings (simple list format)
    """

    # 1. Get company context
    company_context = fetch_articles.get_company_by_id(company_id)
    if not company_context:
        print(f"[ERROR] Company not found: {company_id}")
        return []

    # 2. Fetch articles from recent searches
    articles = fetch_searches.fetch_all_articles_for_ideas(
        num_searches=num_searches,
        articles_per_search=articles_per_search
    )

    if not articles:
        print(f"[WARNING] No articles found from recent searches")
        return []

    # Limit to top 30 articles to avoid token limits (with 500 char text snippets)
    MAX_ARTICLES_FOR_PROMPT = 30
    articles_for_analysis = articles[:MAX_ARTICLES_FOR_PROMPT]

    print(f"[INFO] Found {len(articles)} total articles from {num_searches} recent searches")
    print(f"[INFO] Analyzing top {len(articles_for_analysis)} articles for idea generation...")

    # 3. Build prompt and call GPT
    prompt = _build_ideas_prompt(
        company_name=company_context["name"],
        company_description=company_context["description"],
        competitors=company_context["competitors"],
        articles=articles_for_analysis
    )

    raw_response = gpt.load_model(
        prompt,
        max_tokens=3000,  # Increased for richer output with full text context
        temperature=0.4,  # Slightly higher for more creativity
        stream=False
    )

    # 4. Parse JSON response
    json_str = _extract_json(raw_response)

    try:
        ideas = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse GPT response: {e}")
        return []

    if not isinstance(ideas, list):
        return []

    # 5. Clean and normalize ideas
    cleaned_ideas = []
    for idea_obj in ideas:
        if not isinstance(idea_obj, dict):
            continue

        idea_text = (idea_obj.get("idea") or "").strip()
        if not idea_text:
            continue

        cleaned_ideas.append({
            "idea": idea_text,
            "category": idea_obj.get("category", "general").lower(),
        })

    # 6. Diversify and ensure we have 2-6 ideas
    diversified_ideas = _diversify_ideas(cleaned_ideas)

    # Enforce minimum of 2 and maximum of 6 ideas
    MIN_IDEAS = 2
    MAX_IDEAS = 6

    if len(diversified_ideas) < MIN_IDEAS:
        print(f"[WARNING] Only generated {len(diversified_ideas)} ideas (minimum is {MIN_IDEAS})")

    final_ideas = diversified_ideas[:MAX_IDEAS]

    # Convert to simple list format: just the idea descriptions
    ideas_list = [idea["idea"] for idea in final_ideas]

    print(ideas_list)

    return ideas_list


def print_ideas(ideas_list: List[str]):
    """Pretty print ideas for CLI."""

    if not ideas_list:
        print("[INFO] No ideas generated.")
        return

    print(f"\n{'='*80}")
    print(f"IDEAS (2-6)")
    print(f"{'='*80}")
    print(f"Generated {len(ideas_list)} ideas:\n")

    for i, idea in enumerate(ideas_list, 1):
        print(f"\n{i}. {idea}\n")

    print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate ideas from recent searches")
    parser.add_argument("company_id", help="Company ID from company_profiles")
    parser.add_argument("--searches", type=int, default=10, help="Number of recent searches to analyze")
    parser.add_argument("--articles", type=int, default=10, help="Number of articles per search")

    args = parser.parse_args()

    print(f"[INFO] Generating ideas for company {args.company_id}...")
    ideas_list = generate_ideas(args.company_id, num_searches=args.searches, articles_per_search=args.articles)
    print_ideas(ideas_list)
