"""
Sentiment Analysis Module

A scalable sentiment analysis system for processing unlimited text sizes.
"""

from .sentiment_analyzer import SentimentAnalyzer, SentimentResult, quick_sentiment, analyze_text_dict

__version__ = '1.0.0'
__all__ = ['SentimentAnalyzer', 'SentimentResult', 'quick_sentiment', 'analyze_text_dict']
