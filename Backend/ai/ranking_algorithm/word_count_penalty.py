# AI/ranking_algorithm/word_count_penalty.py
"""
Word count penalty to reduce ranking of very short, low-quality posts.

Problem: Short posts like "I have iPhone 16" get ranked too high because
they contain exact keyword matches but lack substantial content.

Solution: Apply a smooth penalty to posts based on word count:
- Very short posts (< 50 words): Heavy penalty
- Medium posts (50-100 words): Gradual reduction in penalty
- Long posts (> 100 words): No penalty
"""

import re
from typing import Dict, Any


def count_words(text: str) -> int:
    """
    Count words in text, ignoring URLs and special characters.

    Args:
        text: The text to count words in

    Returns:
        Number of words
    """
    if not text:
        return 0

    # Remove URLs
    text = re.sub(r'https?://\S+|www\.\S+', '', text)

    # Split on whitespace and filter out empty strings
    words = [w for w in text.split() if w.strip()]

    return len(words)


def calculate_word_count_multiplier(text: str, min_words: int = 50, target_words: int = 100) -> float:
    """
    Calculate a multiplier based on word count to penalize short posts.

    The multiplier scales from 0.3 to 1.0:
    - Posts < min_words: 0.3x (heavy penalty)
    - Posts between min_words and target_words: gradual increase
    - Posts >= target_words: 1.0x (no penalty)

    This uses a smooth sigmoid-like curve for natural scaling.

    Args:
        text: The text to analyze
        min_words: Minimum words for reduced penalty (default: 50)
        target_words: Words needed for no penalty (default: 100)

    Returns:
        Multiplier between 0.3 and 1.0
    """
    word_count = count_words(text)

    # No text = maximum penalty
    if word_count == 0:
        return 0.1

    # Already meets target - no penalty
    if word_count >= target_words:
        return 1.0

    # Very short - heavy penalty (0.3x)
    if word_count < min_words:
        # Scale from 0.3 at 0 words to 0.5 at min_words
        ratio = word_count / min_words
        return 0.3 + (0.2 * ratio)

    # Medium length - gradual scaling from 0.5 to 1.0
    # Uses smooth curve between min_words and target_words
    ratio = (word_count - min_words) / (target_words - min_words)

    # Smooth curve (ease-in-out)
    smooth_ratio = ratio * ratio * (3.0 - 2.0 * ratio)

    return 0.5 + (0.5 * smooth_ratio)


def apply_word_count_penalty(score: float, text: str,
                             min_words: int = 50,
                             target_words: int = 100,
                             verbose: bool = False) -> float:
    """
    Apply word count penalty to a relevance score.

    Args:
        score: Original relevance score (0-1)
        text: The text to analyze
        min_words: Minimum words for reduced penalty (default: 50)
        target_words: Words needed for no penalty (default: 100)
        verbose: Print debug info

    Returns:
        Penalized score (0-1)
    """
    multiplier = calculate_word_count_multiplier(text, min_words, target_words)
    penalized_score = score * multiplier

    if verbose:
        word_count = count_words(text)
        print(f"[WORD COUNT PENALTY] Words: {word_count}, Multiplier: {multiplier:.2f}, "
              f"Score: {score:.4f} -> {penalized_score:.4f}")

    return penalized_score


# Example usage and testing
if __name__ == "__main__":
    test_cases = [
        ("I have iPhone 16", "Very short post"),
        ("I recently bought the new iPhone 16 and it's amazing!", "Short post"),
        ("The iPhone 16 is Apple's latest flagship smartphone. " * 5, "Medium post"),
        ("The iPhone 16 represents a significant leap forward in mobile technology. " * 10, "Long post"),
    ]

    print("Word Count Penalty Test Cases:")
    print("=" * 80)

    for text, description in test_cases:
        word_count = count_words(text)
        multiplier = calculate_word_count_multiplier(text)
        original_score = 0.95  # Assume high relevance
        penalized_score = apply_word_count_penalty(original_score, text)

        print(f"\n{description}:")
        print(f"  Text: {text[:60]}...")
        print(f"  Word count: {word_count}")
        print(f"  Multiplier: {multiplier:.2f}x")
        print(f"  Score: {original_score:.4f} -> {penalized_score:.4f} ({(penalized_score/original_score)*100:.1f}%)")
