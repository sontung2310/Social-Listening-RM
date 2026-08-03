# AI/Algorithms/combiner.py
"""
Weighted fusion of per-algorithm scores into a final score in [0,1]
"""

from typing import Dict


def weighted_combine(per_algo: Dict[str, float], weights: Dict[str, float]) -> float:
    """
    per_algo: example {"tfidf": 0.42, "sbert": 0.71, "engagement": 0.33}
    weights:  example {"tfidf": 0.35, "sbert": 0.45, "engagement": 0.20}
    """
    if not per_algo or not weights:
        return 0.0
    num = 0.0
    den = 0.0
    for k, w in weights.items():
        den += float(w)
        num += float(per_algo.get(k, 0.0)) * float(w)
    if den <= 0.0:
        return 0.0
    out = num / den
    if out < 0.0:
        return 0.0
    if out > 1.0:
        return 1.0
    return float(out)
