# Text Summarization Package
"""
Fast, non-LLM text summarization using TF-IDF and extractive techniques.

Main Function:
- generate_summary(text): Returns a 4-line summary of any text

Example:
    from ai.Text_summarisation import generate_summary

    article = "..."  # Your long article text
    summary = generate_summary(article)
    print(summary)
"""

from .main_summaries import generate_summary
from .Text_summariser import summarize_text, summarize_text_to_lines
from .summarize_articles import (
    summarize_articles_to_bullets,
    per_article_snippets,
    compact_article_sources,
)

__all__ = [
    "generate_summary",
    "summarize_text",
    "summarize_text_to_lines",
    "summarize_articles_to_bullets",
    "per_article_snippets",
    "compact_article_sources",
]
