# AI/collection_card/ideas/__init__.py
"""
Ideas card module for generating innovative ideas from recent searches.
"""

from . import fetch_searches
from . import generate_ideas
from . import main_ideas

__all__ = [
    "fetch_searches",
    "generate_ideas",
    "main_ideas",
]
