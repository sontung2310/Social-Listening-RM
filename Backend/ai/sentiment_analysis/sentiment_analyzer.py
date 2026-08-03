"""
Sentiment Analysis Module for Large Text Processing

This module provides sentiment analysis capabilities for unlimited text sizes
without using LLMs. It uses efficient transformer models and rule-based methods
that can process text in chunks.
"""

import re
from typing import List, Dict, Tuple, Optional, Union
from dataclasses import dataclass
import numpy as np


@dataclass
class SentimentResult:
    """Container for sentiment analysis results"""
    label: str  # 'positive', 'negative', 'neutral'
    score: float  # Confidence score (0-1)
    positive_score: float
    negative_score: float
    neutral_score: float
    compound_score: float  # Overall sentiment (-1 to 1)
    text_length: int
    num_chunks: int


class SentimentAnalyzer:
    """
    Sentiment analyzer that can handle unlimited text sizes by processing in chunks.
    Supports multiple backends: VADER (rule-based) and Transformer models.
    """

    def __init__(self, method: str = 'vader', chunk_size: int = 512, overlap: int = 50):
        """
        Initialize the sentiment analyzer.

        Args:
            method: 'vader' for rule-based or 'transformer' for deep learning
            chunk_size: Maximum tokens per chunk (for transformer models)
            overlap: Number of tokens to overlap between chunks
        """
        self.method = method.lower()
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.model = None
        self.tokenizer = None
        self.vader_analyzer = None

        self._initialize_model()

    def _initialize_model(self):
        """Initialize the selected sentiment analysis model"""
        if self.method == 'vader':
            try:
                from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
                self.vader_analyzer = SentimentIntensityAnalyzer()
                print("[OK] VADER sentiment analyzer initialized")
            except ImportError:
                raise ImportError(
                    "VADER not found. Install with: pip install vaderSentiment"
                )

        elif self.method == 'transformer':
            try:
                from transformers import pipeline
                # Using a small, efficient model for sentiment analysis
                self.model = pipeline(
                    "sentiment-analysis",
                    model="distilbert-base-uncased-finetuned-sst-2-english",
                    device=-1  # Use CPU, set to 0 for GPU
                )
                print("[OK] Transformer model initialized (DistilBERT)")
            except ImportError:
                raise ImportError(
                    "Transformers not found. Install with: pip install transformers torch"
                )

        elif self.method == 'hybrid':
            # Initialize both for hybrid approach
            self.method = 'vader'
            self._initialize_model()
            self.method = 'transformer'
            transformer_model = self.model
            self.method = 'hybrid'
            self.transformer_model = transformer_model
            try:
                from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
                self.vader_analyzer = SentimentIntensityAnalyzer()
                print("[OK] Hybrid mode initialized (VADER + Transformer)")
            except ImportError:
                raise ImportError("Both VADER and transformers required for hybrid mode")

        else:
            raise ValueError(f"Unknown method: {self.method}. Use 'vader', 'transformer', or 'hybrid'")

    def _chunk_text(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks for processing.

        Args:
            text: Input text to chunk

        Returns:
            List of text chunks
        """
        # Simple sentence-based chunking
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return [text]

        chunks = []
        current_chunk = []
        current_length = 0

        for sentence in sentences:
            # Rough token estimate (words * 1.3)
            sentence_length = len(sentence.split()) * 1.3

            if current_length + sentence_length > self.chunk_size and current_chunk:
                # Save current chunk
                chunks.append(' '.join(current_chunk))
                # Keep last few sentences for overlap
                overlap_sentences = int(len(current_chunk) * (self.overlap / self.chunk_size))
                current_chunk = current_chunk[-overlap_sentences:] if overlap_sentences > 0 else []
                current_length = sum(len(s.split()) * 1.3 for s in current_chunk)

            current_chunk.append(sentence)
            current_length += sentence_length

        # Add remaining chunk
        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks if chunks else [text]

    def _analyze_with_vader(self, text: str) -> Dict[str, float]:
        """Analyze sentiment using VADER"""
        scores = self.vader_analyzer.polarity_scores(text)
        return scores

    def _analyze_with_transformer(self, text: str) -> Dict[str, float]:
        """Analyze sentiment using transformer model"""
        try:
            result = self.model(text[:512])[0]  # Most models have 512 token limit per call
            label = result['label'].lower()
            score = result['score']

            # Convert to unified format
            if label == 'positive':
                return {'pos': score, 'neg': 1 - score, 'neu': 0, 'compound': score}
            else:
                return {'pos': 1 - score, 'neg': score, 'neu': 0, 'compound': -score}
        except Exception as e:
            print(f"Warning: Transformer analysis failed: {e}")
            return {'pos': 0, 'neg': 0, 'neu': 1, 'compound': 0}

    def _aggregate_chunk_scores(self, chunk_scores: List[Dict[str, float]]) -> Dict[str, float]:
        """
        Aggregate sentiment scores from multiple chunks.

        Args:
            chunk_scores: List of score dictionaries from each chunk

        Returns:
            Aggregated scores
        """
        if not chunk_scores:
            return {'pos': 0, 'neg': 0, 'neu': 1, 'compound': 0}

        # Weight by chunk length (all chunks weighted equally for now)
        avg_scores = {
            'pos': np.mean([s['pos'] for s in chunk_scores]),
            'neg': np.mean([s['neg'] for s in chunk_scores]),
            'neu': np.mean([s['neu'] for s in chunk_scores]),
            'compound': np.mean([s['compound'] for s in chunk_scores])
        }

        return avg_scores

    def analyze(self, text: str) -> SentimentResult:
        """
        Analyze sentiment of text of any length.

        Args:
            text: Input text to analyze

        Returns:
            SentimentResult object with detailed scores
        """
        if not text or not text.strip():
            return SentimentResult(
                label='neutral',
                score=1.0,
                positive_score=0.0,
                negative_score=0.0,
                neutral_score=1.0,
                compound_score=0.0,
                text_length=0,
                num_chunks=0
            )

        # Chunk the text
        chunks = self._chunk_text(text)

        # Analyze each chunk
        chunk_scores = []
        for chunk in chunks:
            if self.method == 'vader':
                scores = self._analyze_with_vader(chunk)
            elif self.method == 'transformer':
                scores = self._analyze_with_transformer(chunk)
            elif self.method == 'hybrid':
                vader_scores = self._analyze_with_vader(chunk)
                transformer_scores = self._analyze_with_transformer(chunk)
                # Average the two methods
                scores = {
                    'pos': (vader_scores['pos'] + transformer_scores['pos']) / 2,
                    'neg': (vader_scores['neg'] + transformer_scores['neg']) / 2,
                    'neu': (vader_scores['neu'] + transformer_scores['neu']) / 2,
                    'compound': (vader_scores['compound'] + transformer_scores['compound']) / 2
                }
            else:
                scores = {'pos': 0, 'neg': 0, 'neu': 1, 'compound': 0}

            chunk_scores.append(scores)

        # Aggregate scores
        final_scores = self._aggregate_chunk_scores(chunk_scores)

        # Determine overall label
        if final_scores['compound'] >= 0.05:
            label = 'positive'
            score = final_scores['pos']
        elif final_scores['compound'] <= -0.05:
            label = 'negative'
            score = final_scores['neg']
        else:
            label = 'neutral'
            score = final_scores['neu']

        return SentimentResult(
            label=label,
            score=score,
            positive_score=final_scores['pos'],
            negative_score=final_scores['neg'],
            neutral_score=final_scores['neu'],
            compound_score=final_scores['compound'],
            text_length=len(text),
            num_chunks=len(chunks)
        )

    def analyze_batch(self, texts: List[str]) -> List[SentimentResult]:
        """
        Analyze sentiment for multiple texts.

        Args:
            texts: List of texts to analyze

        Returns:
            List of SentimentResult objects
        """
        return [self.analyze(text) for text in texts]

    def analyze_file(self, file_path: str, encoding: str = 'utf-8') -> SentimentResult:
        """
        Analyze sentiment of a text file.

        Args:
            file_path: Path to text file
            encoding: File encoding

        Returns:
            SentimentResult object
        """
        with open(file_path, 'r', encoding=encoding) as f:
            text = f.read()
        return self.analyze(text)


def quick_sentiment(text: str, method: str = 'vader') -> str:
    """
    Quick sentiment analysis function.

    Args:
        text: Text to analyze
        method: 'vader' or 'transformer'

    Returns:
        Sentiment label: 'positive', 'negative', or 'neutral'
    """
    analyzer = SentimentAnalyzer(method=method)
    result = analyzer.analyze(text)
    return result.label


def analyze_text_dict(data: List[Dict[str, str]], method: str = 'vader') -> List[str]:
    """
    Analyze sentiment from a list of dictionaries containing text.

    Args:
        data: List of dictionaries with 'Text' key, e.g., [{"Text": "example"}]
        method: 'vader' or 'transformer'

    Returns:
        List of sentiment labels: 'Positive', 'Negative', or 'Neutral'
    """
    analyzer = SentimentAnalyzer(method=method)
    results = []

    for item in data:
        if not isinstance(item, dict) or 'Text' not in item:
            raise ValueError("Each item must be a dictionary with a 'Text' key")

        text = item['Text']
        result = analyzer.analyze(text)
        # Capitalize the first letter to match the requested format
        sentiment = result.label.capitalize()
        results.append(sentiment)

    return results


if __name__ == "__main__":
    # Quick test
    test_text = """
    This is an amazing product! I absolutely love it. The quality is outstanding
    and it exceeded all my expectations. However, the delivery was a bit slow,
    which was slightly disappointing. Overall, I'm very satisfied with my purchase
    and would definitely recommend it to others.
    """

    print("Testing VADER sentiment analysis...")
    analyzer = SentimentAnalyzer(method='vader')
    result = analyzer.analyze(test_text)

    print(f"\nSentiment: {result.label.upper()}")
    print(f"Confidence: {result.score:.3f}")
    print(f"Positive: {result.positive_score:.3f}")
    print(f"Negative: {result.negative_score:.3f}")
    print(f"Neutral: {result.neutral_score:.3f}")
    print(f"Compound: {result.compound_score:.3f}")
    print(f"Processed {result.num_chunks} chunks from {result.text_length} characters")
