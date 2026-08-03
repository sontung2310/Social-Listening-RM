# Pace-Unit\AI\Text_summarisation\Text_summariser.py
"""
Fast extractive text summarization without LLM.
Uses TF-IDF + sentence scoring to extract the most important sentences.
"""
from __future__ import annotations
import re
from typing import List, Tuple
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# Sentence splitting regex
_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+')
_WS = re.compile(r'\s+')


def _normalize_text(text: str) -> str:
    """Normalize whitespace in text."""
    return _WS.sub(" ", (text or "").strip())


def _split_into_sentences(text: str) -> List[str]:
    """
    Split text into sentences using regex.
    Returns list of normalized sentences.
    """
    text = _normalize_text(text)
    if not text:
        return []

    sentences = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    # Filter out very short sentences (likely noise)
    return [s for s in sentences if len(s) > 10]


def _score_sentences(sentences: List[str]) -> np.ndarray:
    """
    Score sentences using TF-IDF and cosine similarity to centroid.
    Returns array of scores (higher = more important).
    """
    if len(sentences) <= 1:
        return np.ones(len(sentences))

    # Build TF-IDF matrix
    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        max_df=0.9,
        min_df=1,
        stop_words="english",
    )

    try:
        tfidf_matrix = vectorizer.fit_transform(sentences)
    except ValueError:
        # If all sentences are too similar or empty
        return np.ones(len(sentences))

    # Calculate centroid (average of all sentence vectors)
    centroid = np.asarray(tfidf_matrix.mean(axis=0))

    # Score each sentence by similarity to centroid
    scores = cosine_similarity(tfidf_matrix, centroid).ravel()

    return scores


def _add_diversity_penalty(
    sentences: List[str],
    scores: np.ndarray,
    selected_indices: List[int],
    tfidf_matrix: np.ndarray,
    lambda_: float = 0.7,
) -> np.ndarray:
    """
    Apply MMR-like diversity penalty to avoid redundant sentences.
    """
    if not selected_indices:
        return scores

    # Calculate similarity to already selected sentences
    similarity_matrix = cosine_similarity(tfidf_matrix)

    # For each sentence, find max similarity to any selected sentence
    max_similarity = np.max([similarity_matrix[:, idx] for idx in selected_indices], axis=0)

    # Apply MMR formula: score = λ * relevance - (1-λ) * redundancy
    adjusted_scores = lambda_ * scores - (1 - lambda_) * max_similarity

    return adjusted_scores


def summarize_text(
    text: str,
    num_sentences: int = 5,
    min_sentences: int = 4,
    use_diversity: bool = True,
) -> str:
    """
    Summarize a large text chunk into 4-5 key sentences (no LLM).

    Uses extractive summarization with TF-IDF scoring to identify the most
    important sentences. Optionally applies diversity filtering to avoid
    redundant information.

    Args:
        text: The input text to summarize
        num_sentences: Target number of sentences in summary (default: 5)
        min_sentences: Minimum sentences to return if text is short (default: 4)
        use_diversity: Whether to apply diversity penalty to avoid redundancy (default: True)

    Returns:
        Summary string with the most important sentences in original order.

    Example:
        >>> long_article = "..."
        >>> summary = summarize_text(long_article)
        >>> print(summary)
    """
    # Split into sentences
    sentences = _split_into_sentences(text)

    # If text is already short, return as-is
    if len(sentences) <= num_sentences:
        return " ".join(sentences)

    # Score sentences by importance
    scores = _score_sentences(sentences)

    if use_diversity:
        # Use MMR-style selection for diversity
        selected_indices = []
        vectorizer = TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),
            max_df=0.9,
            min_df=1,
            stop_words="english",
        )
        tfidf_matrix = vectorizer.fit_transform(sentences)

        # Iteratively select sentences
        remaining_indices = set(range(len(sentences)))
        current_scores = scores.copy()

        for _ in range(min(num_sentences, len(sentences))):
            # Find best sentence from remaining
            best_idx = max(remaining_indices, key=lambda i: current_scores[i])
            selected_indices.append(best_idx)
            remaining_indices.remove(best_idx)

            if remaining_indices:
                # Update scores with diversity penalty
                temp_scores = scores.copy()
                temp_scores = _add_diversity_penalty(
                    sentences, temp_scores, selected_indices, tfidf_matrix
                )
                # Zero out already selected
                for idx in selected_indices:
                    temp_scores[idx] = -1e9
                current_scores = temp_scores
    else:
        # Simple: just take top N by score
        selected_indices = np.argsort(scores)[-num_sentences:].tolist()

    # Sort by original position to maintain coherence
    selected_indices.sort()

    # Build summary
    summary_sentences = [sentences[i] for i in selected_indices]
    return " ".join(summary_sentences)


def summarize_text_to_lines(text: str, num_lines: int = 5) -> List[str]:
    """
    Summarize text and return as a list of individual sentences/lines.

    This is useful when you need the summary as separate bullet points or lines
    rather than a single paragraph.

    Args:
        text: The input text to summarize
        num_lines: Number of summary lines to return (default: 5)

    Returns:
        List of summary sentences

    Example:
        >>> summary_lines = summarize_text_to_lines(long_article, num_lines=4)
        >>> for line in summary_lines:
        ...     print(f"• {line}")
    """
    summary = summarize_text(text, num_sentences=num_lines)
    return _split_into_sentences(summary)


if __name__ == "__main__":
    # Quick test
    sample_text = """
    Artificial intelligence has made significant progress in recent years.
    Machine learning models are becoming increasingly sophisticated.
    Deep learning, a subset of machine learning, uses neural networks with multiple layers.
    These neural networks can process vast amounts of data.
    Natural language processing allows computers to understand human language.
    Computer vision enables machines to interpret visual information.
    AI is being applied in healthcare, finance, and many other industries.
    Self-driving cars use AI to navigate roads safely.
    AI assistants like Siri and Alexa have become commonplace.
    However, there are concerns about AI ethics and job displacement.
    Researchers are working on making AI more transparent and interpretable.
    The future of AI holds both promise and challenges.
    """

    print("Original text:")
    print(sample_text)
    print("\n" + "="*80 + "\n")

    print("Summary (5 sentences):")
    summary = summarize_text(sample_text, num_sentences=5)
    print(summary)
    print("\n" + "="*80 + "\n")

    print("Summary as bullet points (4 lines):")
    lines = summarize_text_to_lines(sample_text, num_lines=4)
    for i, line in enumerate(lines, 1):
        print(f"{i}. {line}")
