# AI/collection_card/summarize_articles.py
from __future__ import annotations
from typing import List, Dict, Any, Tuple
import math
import re
import time

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+')
_WS = re.compile(r'\s+')


def _normalize(s: str) -> str:
    return _WS.sub(" ", (s or "").strip())


def _sentences_from(title: str, summary: str) -> List[str]:
    """
    Robust sentence split from title + summary. Title is treated as one sentence.
    """
    out: List[str] = []
    t = _normalize(title)
    if t:
        out.append(t)
    s = _normalize(summary)
    if s:
        out.extend([x.strip() for x in _SENT_SPLIT.split(s) if x.strip()])
    return out


def _build_corpus(articles: List[Dict[str, Any]]) -> Tuple[List[str], List[Tuple[int, int]]]:
    """
    Flatten all article sentences into a single corpus.
    Returns:
        sentences: List[str] (flattened)
        index_map: List[(article_index, sentence_index_within_article)]
    """
    sentences: List[str] = []
    index_map: List[Tuple[int, int]] = []

    for i, a in enumerate(articles):
        sent_list = _sentences_from(a.get("ai_title", ""), a.get("ai_summary", ""))
        for j, s in enumerate(sent_list):
            if len(s) > 4:  # ignore ultra-short noise
                sentences.append(s)
                index_map.append((i, j))
    return sentences, index_map


def _tfidf(sentences: List[str]) -> Tuple[TfidfVectorizer, np.ndarray]:
    """
    TF-IDF matrix for sentences.
    """
    if not sentences:
        return TfidfVectorizer(), np.zeros((0, 0))
    vect = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        max_df=0.9,
        min_df=1,
        stop_words="english",
    )
    X = vect.fit_transform(sentences)
    return vect, X


def _centroid_scores(X: np.ndarray) -> np.ndarray:
    """
    Score each sentence by cosine similarity to the global centroid.
    """
    if X.shape[0] == 0:
        return np.zeros((0,))
    centroid = np.asarray(X.mean(axis=0))
    sims = cosine_similarity(X, centroid)
    return sims.ravel()


def _mmr_select(
    X: np.ndarray,
    base_scores: np.ndarray,
    k: int = 8,
    lambda_: float = 0.75,
) -> List[int]:
    """
    Maximal Marginal Relevance for diversity.
    Select k sentence indices balancing centrality (base_scores) and novelty.
    """
    n = X.shape[0]
    if n == 0 or k <= 0:
        return []

    chosen: List[int] = []
    cand = list(range(n))

    sims_all = cosine_similarity(X) if n <= 3000 else None  # guard RAM for huge corpora

    for _ in range(min(k, n)):
        best_i, best_val = -1, -1e9
        for i in cand:
            rel = float(base_scores[i])
            if not chosen:
                div = 0.0
            else:
                if sims_all is not None:
                    div = max(float(sims_all[i][j]) for j in chosen)
                else:
                    # compute on the fly
                    div = max(float(cosine_similarity(X[i], X[j]).ravel()[0]) for j in chosen)
            mmr = lambda_ * rel - (1 - lambda_) * div
            if mmr > best_val:
                best_val = mmr
                best_i = i
        if best_i < 0:
            break
        chosen.append(best_i)
        cand.remove(best_i)
    return chosen


def summarize_articles_to_bullets(
    articles: List[Dict[str, Any]],
    *,
    max_bullets: int = 8,
) -> List[str]:
    """
    Build diversified bullet points from titles+summaries (no LLM).
    """
    sentences, _imap = _build_corpus(articles)
    if not sentences:
        return []

    _, X = _tfidf(sentences)
    if X.shape[0] == 0:
        return []

    cent = _centroid_scores(X)
    picks = _mmr_select(X, cent, k=max_bullets, lambda_=0.75)

    bullets: List[str] = []
    for idx in picks:
        s = sentences[idx]
        s = s.rstrip(". ").strip()
        if not s.endswith((".", "!", "?")):
            s = s + "."
        bullets.append(s)
    return bullets


def _first_sentence(text: str) -> str:
    text = _normalize(text)
    if not text:
        return ""
    parts = [x.strip() for x in _SENT_SPLIT.split(text) if x.strip()]
    return parts[0] if parts else text


def _truncate(s: str, max_chars: int) -> str:
    s = (s or "").strip()
    if len(s) <= max_chars:
        return s
    # cut on a word boundary if possible
    cut = s[:max_chars].rsplit(" ", 1)[0]
    return (cut or s[:max_chars]).rstrip() + "…"


def per_article_snippets(
    articles: List[Dict[str, Any]],
    *,
    max_chars: int = 220,
) -> List[Dict[str, Any]]:
    """
    Produce a compact, per-article snippet suitable for cards/lists (LLM-free).
    Strategy:
      - prefer first sentence of ai_summary; if missing, fall back to ai_title
      - normalize, then truncate to max_chars
    """
    out: List[Dict[str, Any]] = []
    for a in articles:
        title = a.get("ai_title", "") or ""
        summ = a.get("ai_summary", "") or ""
        snippet_src = _first_sentence(summ) or _first_sentence(title) or ""
        snippet = _truncate(snippet_src, max_chars=max_chars)

        out.append({
            "ai_title": title,
            "snippet": snippet,
            "url": a.get("url", "") or "",
            "source": a.get("source", "") or "",
            "published_ts": int(a.get("published_ts", time.time())),
            "relevance_score": float(a.get("relevance_score", 0.0)),
            "tags": a.get("tags", []),
        })
    # optional: sort by recency then relevance for UI friendliness
    out.sort(key=lambda r: (r["published_ts"], r["relevance_score"]), reverse=True)
    return out


def compact_article_sources(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Minimal source list for the UI.
    """
    out: List[Dict[str, Any]] = []
    for a in articles:
        out.append({
            "ai_title": a.get("ai_title", ""),
            "url": a.get("url", ""),
            "source": a.get("source", ""),
            "published_ts": int(a.get("published_ts", time.time())),
            "relevance_score": float(a.get("relevance_score", 0.0)),
        })
    # keep it consistent with snippets ordering
    out.sort(key=lambda r: (r["published_ts"], r["relevance_score"]), reverse=True)
    return out
