# AI/Text_summarisation/main_summaries.py
"""
Simple text summarization function.
Accepts text and returns a 4-line summary without using LLM.
"""
from __future__ import annotations
from ai.Text_summarisation.Text_summariser import summarize_text


def generate_summary(text: str) -> str:
    """
    Generate a 4-line summary from any text input.

    Args:
        text: The input text to summarize (can be large)

    Returns:
        A string containing 4 sentences summarizing the key points

    Example:
        >>> article = "Long article text here..."
        >>> summary = generate_summary(article)
        >>> print(summary)
    """
    return summarize_text(text, num_sentences=4)
