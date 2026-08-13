"""Main enrichment pipeline: clean → parallel Call A/B → validate → merge."""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from ai.enrichment.chunking import (
    majority_topic,
    mean_sentiment,
    merge_keywords,
    reduce_summaries,
    split_chunks,
)
from ai.enrichment.clean import clean_text, head_tail_cap
from ai.enrichment.fallbacks import build_fallback_result
from ai.enrichment.llm_client import LLMClient, LLMResponse
from ai.enrichment.logging_util import log_step, preview
from ai.enrichment.prompts import classify_v1, extract_v1
from ai.enrichment import settings as nlp_settings
from ai.enrichment.taxonomy import PROMPT_VERSION
from ai.enrichment.validate import (
    extract_json_object,
    merge_enrichment,
    validate_classify,
    validate_extract,
)


MIN_LLM_CHARS = 20


def _summary_min_chars() -> int:
    return nlp_settings.get_summary_min_chars()


def _long_chars() -> int:
    return nlp_settings.get_long_chars()


@dataclass
class EnrichmentResult:
    sentiment: Dict[str, Any]
    topics: List[str]
    topic_confidence: float
    keywords: List[Dict[str, Any]]
    summary: str
    entities: List[Any] = field(default_factory=list)
    nlp_meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _call_classify(client: LLMClient, text: str) -> tuple[Dict[str, Any], LLMResponse, List[str]]:
    messages = classify_v1.build_messages(text)
    # GPT-5* may spend completion budget on reasoning; allow more headroom.
    max_tok = 1024 if "gpt-5" in (client.backup_model or "").lower() else 256
    resp = client.chat(messages, event_prefix="CALL_A", max_tokens=max_tok)
    if not resp.ok:
        return {}, resp, ["classify_failed"]
    obj = extract_json_object(resp.content)
    if obj is None and (os.getenv("NLP_SKIP_JSON_REPAIR") or "").strip() not in {
        "1",
        "true",
        "yes",
    }:
        # one repair retry same provider path via client (full failover again)
        repair_msgs = messages + [
            {
                "role": "user",
                "content": "Your previous reply was invalid. Reply with JSON only, no markdown.",
            }
        ]
        resp2 = client.chat(repair_msgs, event_prefix="CALL_A", max_tokens=max_tok)
        if resp2.ok:
            resp = resp2
            obj = extract_json_object(resp.content)
    validated, notes = validate_classify(obj)
    return validated, resp, notes


def _call_extract(
    client: LLMClient, text: str, *, summarize: bool
) -> tuple[Dict[str, Any], LLMResponse, List[str]]:
    messages = extract_v1.build_messages(text, summarize=summarize)
    max_tok = 2048 if "gpt-5" in (client.backup_model or "").lower() else 512
    resp = client.chat(messages, event_prefix="CALL_B", max_tokens=max_tok)
    if not resp.ok:
        return {}, resp, ["extract_failed"]
    obj = extract_json_object(resp.content)
    if obj is None and (os.getenv("NLP_SKIP_JSON_REPAIR") or "").strip() not in {
        "1",
        "true",
        "yes",
    }:
        repair_msgs = messages + [
            {
                "role": "user",
                "content": "Your previous reply was invalid. Reply with JSON only, no markdown.",
            }
        ]
        resp2 = client.chat(repair_msgs, event_prefix="CALL_B", max_tokens=max_tok)
        if resp2.ok:
            resp = resp2
            obj = extract_json_object(resp.content)
    validated, notes = validate_extract(obj, text, allow_summary=summarize)
    return validated, resp, notes


def _enrich_sync_segment(
    client: LLMClient,
    text: str,
    *,
    summarize: bool,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Run Call A ‖ Call B on one text segment. Returns (merged, meta)."""
    capped = head_tail_cap(text, 6000)
    classify_out: Dict[str, Any] = {}
    extract_out: Dict[str, Any] = {}
    c_notes: List[str] = []
    e_notes: List[str] = []
    c_resp: Optional[LLMResponse] = None
    e_resp: Optional[LLMResponse] = None

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_a = pool.submit(_call_classify, client, capped)
        fut_b = pool.submit(_call_extract, client, capped, summarize=summarize)
        for fut in as_completed([fut_a, fut_b]):
            if fut is fut_a:
                classify_out, c_resp, c_notes = fut.result()
            else:
                extract_out, e_resp, e_notes = fut.result()

    degraded = False
    providers = []
    models = []
    latency = 0.0
    if c_resp:
        providers.append(c_resp.provider)
        models.append(c_resp.model)
        latency = max(latency, c_resp.latency_ms)
        if not c_resp.ok:
            degraded = True
    if e_resp:
        providers.append(e_resp.provider)
        models.append(e_resp.model)
        latency = max(latency, e_resp.latency_ms)
        if not e_resp.ok:
            degraded = True

    if not classify_out and not extract_out:
        merged = build_fallback_result(text, allow_summary=summarize)
        degraded = True
        log_step("FALLBACK", reason="both_calls_failed")
    elif not classify_out:
        fb = build_fallback_result(text, allow_summary=False)
        classify_out = {
            "sentiment": fb["sentiment"],
            "topic": "Other",
            "topic_confidence": 0.0,
        }
        c_notes.append("classify_fallback")
        degraded = True
        merged = merge_enrichment(classify_out, extract_out, classify_notes=c_notes, extract_notes=e_notes)
    elif not extract_out:
        fb = build_fallback_result(text, allow_summary=summarize)
        extract_out = {"keywords": fb["keywords"], "summary": fb["summary"]}
        e_notes.append("extract_fallback")
        degraded = True
        merged = merge_enrichment(classify_out, extract_out, classify_notes=c_notes, extract_notes=e_notes)
    else:
        merged = merge_enrichment(classify_out, extract_out, classify_notes=c_notes, extract_notes=e_notes)

    meta = {
        "providers": providers,
        "models": models,
        "segment_latency_ms": round(latency, 1),
        "degraded": degraded,
    }
    return merged, meta


def _enrich_long_chunked(client: LLMClient, text: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    chunks = split_chunks(text, chunk_size=1500, overlap=100)
    log_step("GATE", route="async_long", chunks=len(chunks), chars=len(text))
    classify_parts: List[Dict[str, Any]] = []
    keyword_parts: List[List[Dict[str, Any]]] = []
    summaries: List[str] = []
    providers: List[str] = []
    models: List[str] = []
    degraded = False
    total_latency = 0.0

    for i, chunk in enumerate(chunks):
        summarize_chunk = True  # always ask short summary per chunk for reduce
        merged, meta = _enrich_sync_segment(client, chunk, summarize=summarize_chunk)
        classify_parts.append(
            {
                "label": (merged.get("sentiment") or {}).get("label"),
                "score": (merged.get("sentiment") or {}).get("score"),
                "topic": (merged.get("topics") or ["Other"])[0],
                "topic_confidence": merged.get("topic_confidence"),
            }
        )
        keyword_parts.append(merged.get("keywords") or [])
        if merged.get("summary"):
            summaries.append(merged["summary"])
        providers.extend(meta.get("providers") or [])
        models.extend(meta.get("models") or [])
        total_latency += float(meta.get("segment_latency_ms") or 0)
        if meta.get("degraded"):
            degraded = True
        log_step("CHUNK", index=i, keywords=len(merged.get("keywords") or []))

    topic = majority_topic([p.get("topic") or "Other" for p in classify_parts])
    sentiment = mean_sentiment(classify_parts)
    confs = [float(p.get("topic_confidence") or 0) for p in classify_parts]
    conf = sum(confs) / len(confs) if confs else 0.0
    result = {
        "sentiment": sentiment,
        "topics": [topic],
        "topic_confidence": round(conf, 4),
        "keywords": merge_keywords(keyword_parts),
        "summary": reduce_summaries(summaries),
        "entities": [],
    }
    meta = {
        "providers": list(dict.fromkeys(providers)),
        "models": list(dict.fromkeys(models)),
        "segment_latency_ms": round(total_latency, 1),
        "degraded": degraded,
        "chunked": True,
        "chunks": len(chunks),
    }
    return result, meta


def enrich_text(
    text: str,
    *,
    source: str = "",
    external_id: str = "",
    content_type: str = "",
    force_sync: bool = False,
    client: Optional[LLMClient] = None,
) -> EnrichmentResult:
    """
    Enrich a single text.

    For len >= LONG_CHARS, runs chunked enrichment inline (caller may treat
    nlp_status as pending when force_sync=False and schedule async separately;
    this function always returns a complete result when called).
    """
    t0 = time.perf_counter()
    client = client or LLMClient()
    log_step(
        "START",
        source=source,
        external_id=external_id,
        content_type=content_type,
        text_chars=len(text or ""),
        preview=preview(text),
    )

    cleaned, cin, cout = clean_text(text)
    log_step("CLEAN", chars_in=cin, chars_out=cout)

    summary_min = _summary_min_chars()
    long_chars = _long_chars()
    allow_summary = len(cleaned) >= summary_min

    if len(cleaned) < MIN_LLM_CHARS:
        log_step("GATE", route="skip_short", chars=len(cleaned))
        result = {
            "sentiment": {"label": "neutral", "score": 0.0},
            "topics": ["Other"],
            "topic_confidence": 0.0,
            "keywords": [],
            "summary": "",
            "entities": [],
        }
        meta = {
            "provider": "skip",
            "model": "",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "degraded": False,
            "nlp_status": "ready",
            "prompt_version": PROMPT_VERSION,
            "chunked": False,
            "skipped": True,
        }
        log_step("DONE", **{k: meta[k] for k in ("latency_ms", "nlp_status")})
        return EnrichmentResult(
            sentiment=result["sentiment"],
            topics=result["topics"],
            topic_confidence=result["topic_confidence"],
            keywords=result["keywords"],
            summary=result["summary"],
            entities=[],
            nlp_meta=meta,
        )

    if len(cleaned) >= long_chars:
        # Worker may upsert pending first; enrich_text still returns full chunked result
        # when invoked (eval / async follow-up / force_sync).
        log_step(
            "GATE",
            route="sync_forced_long" if force_sync else "async_long",
            chars=len(cleaned),
        )
        merged, seg_meta = _enrich_long_chunked(client, cleaned)
        nlp_status = "ready"
    else:
        log_step("GATE", route="sync", chars=len(cleaned), summarize=allow_summary)
        merged, seg_meta = _enrich_sync_segment(client, cleaned, summarize=allow_summary)
        nlp_status = "ready"

    total_ms = (time.perf_counter() - t0) * 1000.0
    providers = seg_meta.get("providers") or []
    models = seg_meta.get("models") or []
    meta = {
        "provider": providers[0] if providers else "unknown",
        "providers": providers,
        "model": models[0] if models else "",
        "models": models,
        "latency_ms": round(total_ms, 1),
        "degraded": bool(seg_meta.get("degraded")),
        "nlp_status": nlp_status,
        "prompt_version": PROMPT_VERSION,
        "chunked": bool(seg_meta.get("chunked")),
        "chunks": seg_meta.get("chunks"),
    }

    log_step(
        "MERGE",
        sentiment=(merged.get("sentiment") or {}).get("label"),
        topics=merged.get("topics"),
        keyword_count=len(merged.get("keywords") or []),
        summary_preview=preview(merged.get("summary") or "", 120),
        degraded=meta["degraded"],
    )
    log_step("DONE", latency_ms=meta["latency_ms"], nlp_status=nlp_status)

    return EnrichmentResult(
        sentiment=merged.get("sentiment") or {"label": "neutral", "score": 0.0},
        topics=list(merged.get("topics") or ["Other"]),
        topic_confidence=float(merged.get("topic_confidence") or 0.0),
        keywords=list(merged.get("keywords") or []),
        summary=merged.get("summary") or "",
        entities=[],
        nlp_meta=meta,
    )


def pending_stub_result(text: str) -> EnrichmentResult:
    """Minimal result for sync upsert when deferring long-text enrichment."""
    cleaned, _, _ = clean_text(text)
    return EnrichmentResult(
        sentiment={"label": "neutral", "score": 0.0},
        topics=["Other"],
        topic_confidence=0.0,
        keywords=[],
        summary="",
        entities=[],
        nlp_meta={
            "provider": "pending",
            "model": "",
            "latency_ms": 0.0,
            "degraded": False,
            "nlp_status": "pending",
            "prompt_version": PROMPT_VERSION,
            "chunked": True,
            "pending_chars": len(cleaned),
        },
    )
