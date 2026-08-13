"""Run enrichment over fixture; write heuristic scorecard."""
from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from ai.enrichment.logging_util import log_step
from ai.enrichment.pipeline import enrich_text
from ai.enrichment.taxonomy import TOPIC_SET
from ai.enrichment.eval.sample_from_mongo import load_fixture

logger = logging.getLogger("ai.enrichment")


def _keyword_in_text_rate(keywords: List[Dict[str, Any]], text: str) -> float:
    if not keywords:
        return 1.0
    hay = (text or "").lower()
    ok = 0
    for kw in keywords:
        term = (kw.get("term") or "").lower()
        if term and term in hay:
            ok += 1
    return ok / len(keywords)


def run_enrichment_eval(
    fixture: Dict[str, Any],
    *,
    limit: int | None = None,
    out_path: Path | None = None,
) -> Dict[str, Any]:
    samples = list(fixture.get("samples") or [])
    if limit is not None:
        samples = samples[:limit]

    rows: List[Dict[str, Any]] = []
    parse_ok = 0
    topic_ok = 0
    kw_rates: List[float] = []
    latencies: List[float] = []
    sync_latencies: List[float] = []

    for i, sample in enumerate(samples):
        text = sample.get("text") or ""
        t0 = time.perf_counter()
        try:
            result = enrich_text(
                text,
                source=sample.get("source") or "",
                external_id=sample.get("external_id") or sample.get("id") or "",
                content_type=sample.get("content_type") or "",
            )
            err = None
        except Exception as exc:
            logger.exception("[EVAL] sample failed id=%s", sample.get("id"))
            result = None
            err = f"{type(exc).__name__}: {exc}"

        wall_ms = (time.perf_counter() - t0) * 1000.0
        if result is None:
            rows.append(
                {
                    "id": sample.get("id"),
                    "source": sample.get("source"),
                    "content_type": sample.get("content_type"),
                    "text_chars": sample.get("text_chars"),
                    "error": err,
                    "ok": False,
                }
            )
            continue

        d = result.to_dict()
        meta = d.get("nlp_meta") or {}
        topics = d.get("topics") or []
        topic = topics[0] if topics else ""
        topic_valid = topic in TOPIC_SET
        if topic_valid:
            topic_ok += 1
        # treat non-exception + ready as parse success (validation always produces JSON-shaped result)
        parse_ok += 1
        kw_rate = _keyword_in_text_rate(d.get("keywords") or [], text)
        kw_rates.append(kw_rate)
        lat = float(meta.get("latency_ms") or wall_ms)
        latencies.append(lat)
        if not meta.get("chunked") and not meta.get("skipped"):
            sync_latencies.append(lat)

        rows.append(
            {
                "id": sample.get("id"),
                "source": sample.get("source"),
                "content_type": sample.get("content_type"),
                "text_chars": len(text),
                "text_preview": " ".join(text.split())[:160],
                "sentiment": d.get("sentiment"),
                "topics": topics,
                "topic_confidence": d.get("topic_confidence"),
                "keywords": d.get("keywords"),
                "summary": d.get("summary"),
                "nlp_meta": meta,
                "keyword_in_text_rate": round(kw_rate, 4),
                "topic_in_taxonomy": topic_valid,
                "ok": True,
                "wall_ms": round(wall_ms, 1),
            }
        )
        log_step(
            "EVAL_ROW",
            i=i,
            source=sample.get("source"),
            sentiment=(d.get("sentiment") or {}).get("label"),
            topic=topic,
            kw=len(d.get("keywords") or []),
            latency_ms=meta.get("latency_ms"),
        )

    n = len(samples) or 1
    sync_sorted = sorted(sync_latencies)
    p95 = (
        sync_sorted[int(0.95 * (len(sync_sorted) - 1))]
        if sync_sorted
        else None
    )
    report = {
        "n": len(samples),
        "parse_success_rate": round(parse_ok / n, 4),
        "topic_in_taxonomy_rate": round(topic_ok / n, 4),
        "keyword_in_text_rate_mean": round(statistics.mean(kw_rates), 4) if kw_rates else None,
        "latency_ms_mean": round(statistics.mean(latencies), 1) if latencies else None,
        "latency_ms_p95_sync": round(p95, 1) if p95 is not None else None,
        "rows": rows,
    }

    out_path = out_path or (
        Path(__file__).resolve().parent / "reports" / "enrichment_round_0.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "[EVAL] wrote %s parse=%.3f topic=%.3f kw=%.3f p95_sync=%s",
        out_path,
        report["parse_success_rate"],
        report["topic_in_taxonomy_rate"],
        report["keyword_in_text_rate_mean"] or 0,
        report["latency_ms_p95_sync"],
    )
    return report


def main(argv: List[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(description="Run enrichment eval on Mongo fixture")
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--build-sample", action="store_true")
    args = parser.parse_args(argv)

    if args.build_sample:
        from ai.enrichment.eval.sample_from_mongo import build_sample, save_fixture

        data = build_sample()
        save_fixture(data, args.fixture)
        fixture = data
    else:
        fixture = load_fixture(args.fixture)

    run_enrichment_eval(fixture, limit=args.limit, out_path=args.out)
    return 0


if __name__ == "__main__":
    # Ensure Backend is on path
    backend = Path(__file__).resolve().parents[3]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    raise SystemExit(main())
