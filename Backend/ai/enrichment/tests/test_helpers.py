"""Offline unit checks for enrichment helpers (no network)."""
from __future__ import annotations

from ai.enrichment.chunking import merge_keywords, split_chunks
from ai.enrichment.clean import clean_text
from ai.enrichment.validate import extract_json_object, validate_classify, validate_extract


def test_clean_strips_url_and_html():
    cleaned, cin, cout = clean_text('<p>Hello</p> see https://example.com now')
    assert "Hello" in cleaned
    assert "http" not in cleaned.lower()
    assert cout < cin


def test_split_chunks_overlap():
    text = "a" * 3500
    chunks = split_chunks(text, chunk_size=1500, overlap=100)
    assert len(chunks) >= 3


def test_validate_classify_clamps_topic():
    obj, notes = validate_classify(
        {"sentiment": {"label": "POSITIVE", "score": 1.5}, "topic": "Sports", "topic_confidence": 0.2}
    )
    assert obj["sentiment"]["label"] == "neutral" or obj["sentiment"]["label"] == "positive"
    # POSITIVE lowercases to positive
    obj2, _ = validate_classify(
        {"sentiment": {"label": "positive", "score": 0.9}, "topic": "Sports", "topic_confidence": 0.2}
    )
    assert obj2["topic"] == "Other"
    assert any("topic_clamp" in n for n in _)


def test_validate_extract_filters_keywords():
    text = "content marketing improved lead quality for saas"
    obj, notes = validate_extract(
        {
            "keywords": [
                {"term": "content marketing", "score": 0.9},
                {"term": "blockchain moon", "score": 0.8},
            ],
            "summary": "should drop",
        },
        text,
        allow_summary=False,
    )
    terms = [k["term"] for k in obj["keywords"]]
    assert "content marketing" in terms
    assert "blockchain moon" not in terms
    assert obj["summary"] == ""


def test_extract_json_fence():
    raw = '```json\n{"topic":"News"}\n```'
    assert extract_json_object(raw) == {"topic": "News"}


def test_merge_keywords():
    merged = merge_keywords(
        [
            [{"term": "ai", "score": 0.5}],
            [{"term": "ai", "score": 0.9}, {"term": "cloud", "score": 0.7}],
        ]
    )
    assert merged[0]["term"] == "ai"
    assert merged[0]["score"] == 0.9


if __name__ == "__main__":
    test_clean_strips_url_and_html()
    test_split_chunks_overlap()
    test_validate_classify_clamps_topic()
    test_validate_extract_filters_keywords()
    test_extract_json_fence()
    test_merge_keywords()
    print("ok")
