# AI/ranking_algorithm/sbert_scorer.py
"""
SBERT cosine similarity for a query vs. an article.
Returns a semantic similarity score in [0,1].
"""

from typing import Union, Dict, Any

try:
    from sentence_transformers import SentenceTransformer, util
except Exception:
    SentenceTransformer = None
    util = None

_model = None

def _get_model():
    """
    Lazy-load the model once.
    We use a small, fast sentence embedding model.
    """
    global _model
    if _model is None:
        if SentenceTransformer is None:
            raise RuntimeError(
                "sentence-transformers not available. Install it to use SBERT scoring."
            )
        _model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _model

def _clean_text(x) -> str:
    if x is None:
        return ""
    if not isinstance(x, str):
        x = str(x)
    return x.strip()

def sbert_score_one(keyword: str,
                    doc_or_text: Union[str, Dict[str, Any]]) -> float:
    """
    Supports either:
    - raw string text
    - dict with 'text' or ('title' + 'body')
    Returns float in [0,1].
    """
    if isinstance(doc_or_text, str):
        text = _clean_text(doc_or_text)
    else:
        # dict-like
        if doc_or_text.get("text"):
            text = _clean_text(doc_or_text.get("text"))
        else:
            title = _clean_text(doc_or_text.get("title"))
            body = _clean_text(doc_or_text.get("body"))
            text = f"{title}\n{body}".strip()

    if not keyword or not text:
        return 0.0
    print(f"[DEBUG] SBERT scoring doc with text_length={len(text)}")
    m = _get_model()
    q_emb = m.encode(keyword, normalize_embeddings=True)
    d_emb = m.encode(text, normalize_embeddings=True)

    sim = float(util.cos_sim(q_emb, d_emb).item())  # [-1,1]
    # map [-1,1] -> [0,1]
    scaled = (sim + 1.0) / 2.0
    if scaled < 0.0:
        return 0.0
    if scaled > 1.0:
        return 1.0
    return scaled
