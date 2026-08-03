# AI/ranking_algorithm/bm25_scorer.py
from __future__ import annotations
from typing import List, Dict, Any
from rank_bm25 import BM25Okapi
import numpy as np
import re

_word = re.compile(r"[A-Za-z0-9]+")
def _tok(s: str) -> List[str]:
    if not s:
        return []
    return _word.findall(s.lower())

class BM25Scorer:
    """
    Fit once on the current batch of docs, then score a query against all docs.
    Keep an index: doc_id -> position, so we can fetch per-doc scores quickly.
    """

    def __init__(self, bm25: BM25Okapi, id_at_idx: List[Any], idx_of_id: Dict[Any, int]):
        self._bm25 = bm25
        self._id_at_idx = id_at_idx
        self._idx_of_id = idx_of_id

    @classmethod
    def from_docs(cls, docs: List[Dict[str, Any]], *, k1: float = 1.5, b: float = 0.75) -> "BM25Scorer":
        """
        Build a BM25 index over docs.
        We prefer doc["text"] (your current pipeline),
        but fall back to (title + body) for older data.
        """
        id_at_idx: List[Any] = []
        corpus_tokens: List[List[str]] = []

        for d in docs:
            did = d.get("_id")

            # prefer full text field
            if "text" in d and d["text"]:
                text = str(d["text"]).strip()
            else:
                title = (d.get("title") or "").strip()
                body = (d.get("body") or "").strip()
                text = f"{title}\n{body}".strip()

            tokens = _tok(text)
            id_at_idx.append(did)
            corpus_tokens.append(tokens)

        bm25 = BM25Okapi(corpus_tokens, k1=k1, b=b)
        idx_of_id = {did: i for i, did in enumerate(id_at_idx)}
        return cls(bm25=bm25, id_at_idx=id_at_idx, idx_of_id=idx_of_id)

    def score_all_for_query(self, query: str) -> Dict[Any, float]:
        """Return {doc_id: raw_bm25_score} for the query across the whole corpus."""
        qtok = _tok(query or "")
        if not qtok:
            return {did: 0.0 for did in self._id_at_idx}
        scores = self._bm25.get_scores(qtok)  # np.ndarray aligned to id_at_idx
        return {did: float(scores[i]) for i, did in enumerate(self._id_at_idx)}

    def score_for_doc(self, query: str, doc_id: Any) -> float:
        """Score a single doc by id (convenience)."""
        idx = self._idx_of_id.get(doc_id)
        if idx is None:
            return 0.0
        qtok = _tok(query or "")
        if not qtok:
            return 0.0
        scores = self._bm25.get_scores(qtok)
        return float(scores[idx])


def minmax_normalize(score_map: Dict[Any, float]) -> Dict[Any, float]:
    """
    Scale raw BM25 to 0..1 per batch for easier fusion with SBERT/others.
    Safe for empty / constant maps.
    """
    if not score_map:
        return {}
    vals = np.array(list(score_map.values()), dtype=float)
    lo = float(vals.min())
    hi = float(vals.max())
    if hi <= lo:
        return {k: 0.0 for k in score_map}
    return {k: (v - lo) / (hi - lo) for k, v in score_map.items()}
