# AI/ranking_algorithm/tf_idf_scorer.py
from typing import Dict, Any, Union
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

TITLE_BOOST_DEFAULT = 1.15
USE_BIGRAMS_DEFAULT = False

def _clean_text(x) -> str:
    if x is None:
        return ""
    if not isinstance(x, str):
        x = str(x)
    return x.strip()

def _tfidf_pair_cosine(query: str, text: str, use_bigrams: bool = False) -> float:
    query = _clean_text(query)
    text  = _clean_text(text)
    if not query or not text:
        return 0.0
    ngram = (1, 2) if use_bigrams else (1, 1)
    X = TfidfVectorizer(stop_words="english", ngram_range=ngram).fit_transform([query, text])
    sim = float(linear_kernel(X[0:1], X[1:2])[0, 0])
    # clip to [0,1]
    if sim < 0.0:
        return 0.0
    if sim > 1.0:
        return 1.0
    return sim

def _score_title_body(keyword: str, title: str, body: str,
                      *, title_boost: float, use_bigrams: bool) -> float:
    s_title = _tfidf_pair_cosine(keyword, title, use_bigrams)
    s_body  = _tfidf_pair_cosine(keyword, body,  use_bigrams)
    score = title_boost * s_title + s_body
    # clamp
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return score

def score_tfidf_simple(keyword: str,
                       doc_or_text: Union[str, Dict[str, Any]]) -> float:
    """
    Flexible wrapper:
    - If you pass a dict with 'title'/'body', it will use both and apply title_boost.
    - If you pass a dict with only 'text', it will just score that.
    - If you pass a raw string, it will just score that.
    """
    if isinstance(doc_or_text, str):
        body_text = _clean_text(doc_or_text)
        return _tfidf_pair_cosine(keyword, body_text, USE_BIGRAMS_DEFAULT)

    # assume dict-like
    title = _clean_text(doc_or_text.get("title"))
    body  = _clean_text(doc_or_text.get("body"))
    text  = _clean_text(doc_or_text.get("text"))

    if text:
        # single-block text mode
        return _tfidf_pair_cosine(keyword, text, USE_BIGRAMS_DEFAULT)

    # legacy mode with title/body
    return _score_title_body(
        keyword,
        title,
        body,
        title_boost=TITLE_BOOST_DEFAULT,
        use_bigrams=USE_BIGRAMS_DEFAULT,
    )
