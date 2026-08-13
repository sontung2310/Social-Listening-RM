"""Compare enrichment models on the 200-row fixture (accuracy, speed, cost)."""
from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Official OpenAI list prices (USD per 1M tokens) as of docs fetch Aug 2026.
# Sources: developers.openai.com/api/docs/models/gpt-4o-mini and gpt-5-nano
MODEL_PRICES = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-5-nano": {"input": 0.05, "output": 0.40},
    # Judge is excluded from model-vs-model cost; listed for transparency
    "gpt-5.6-luna": {"input": 0.20, "output": 1.20},
    # OpenRouter free router / :free models — $0 list price
    "openrouter/free": {"input": 0.0, "output": 0.0},
}


def _is_openrouter_model(model: str) -> bool:
    m = (model or "").strip().lower()
    return m.startswith("openrouter/") or "/free" in m or m.endswith(":free")


def _cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    prices = MODEL_PRICES.get(model) or {"input": 0.0, "output": 0.0}
    return (prompt_tokens / 1_000_000.0) * prices["input"] + (
        completion_tokens / 1_000_000.0
    ) * prices["output"]


def _p95(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    return s[int(0.95 * (len(s) - 1))]


def run_model(
    model: str,
    fixture: Dict[str, Any],
    *,
    out_dir: Path,
    judge: bool = True,
    limit: Optional[int] = None,
    timeout_ms: int = 15000,
    concurrency: int = 1,
) -> Dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from ai.enrichment.eval.judge import run_judge
    from ai.enrichment.eval.run import _keyword_in_text_rate
    from ai.enrichment.llm_client import LLMClient
    from ai.enrichment.pipeline import enrich_text
    from ai.enrichment.taxonomy import TOPIC_SET

    use_openrouter = _is_openrouter_model(model)
    if use_openrouter:
        # Fair free-tier eval: OpenRouter only (no OpenAI paid failover).
        os.environ["NLP_OPENROUTER_ONLY"] = "1"
        os.environ.pop("NLP_OPENAI_ONLY", None)
        os.environ.pop("NLP_PREFER_OPENAI_PRIMARY", None)
        os.environ["NLP_PRIMARY_MODEL"] = model
        # Free models are slow; skip JSON repair which often doubles wall time.
        os.environ["NLP_SKIP_JSON_REPAIR"] = "1"
    else:
        # Force OpenAI-only so comparison is not polluted by OpenRouter free.
        os.environ.pop("NLP_OPENROUTER_ONLY", None)
        os.environ.pop("NLP_SKIP_JSON_REPAIR", None)
        os.environ["NLP_OPENAI_ONLY"] = "1"
        os.environ["NLP_PREFER_OPENAI_PRIMARY"] = "1"
        os.environ["NLP_BACKUP_MODEL"] = model
    os.environ["NLP_TIMEOUT_MS"] = str(timeout_ms)

    samples = list(fixture.get("samples") or [])
    if limit is not None:
        samples = samples[:limit]

    def _make_client() -> LLMClient:
        c = LLMClient()
        if use_openrouter:
            c.primary_model = model
        else:
            c.backup_model = model
        c.timeout_s = timeout_ms / 1000.0
        c.reset_usage()
        return c

    def _enrich_one(sample: Dict[str, Any]) -> Dict[str, Any]:
        client = _make_client()
        text = sample.get("text") or ""
        t0 = time.perf_counter()
        try:
            result = enrich_text(
                text,
                source=sample.get("source") or "",
                external_id=sample.get("external_id") or sample.get("id") or "",
                content_type=sample.get("content_type") or "",
                client=client,
            )
            err = None
        except Exception as exc:
            result = None
            err = f"{type(exc).__name__}: {exc}"
        wall_ms = (time.perf_counter() - t0) * 1000.0
        usage = client.usage_snapshot()

        if result is None:
            return {
                "id": sample.get("id"),
                "source": sample.get("source"),
                "content_type": sample.get("content_type"),
                "ok": False,
                "error": err,
                "wall_ms": round(wall_ms, 1),
                "_usage": usage,
            }

        d = result.to_dict()
        meta = d.get("nlp_meta") or {}
        topics = d.get("topics") or []
        topic = topics[0] if topics else ""
        kw_rate = _keyword_in_text_rate(d.get("keywords") or [], text)
        lat = float(meta.get("latency_ms") or wall_ms)
        return {
            "id": sample.get("id"),
            "source": sample.get("source"),
            "content_type": sample.get("content_type"),
            "text_chars": len(text),
            "text_preview": " ".join(text.split())[:160],
            "text": text,
            "sentiment": d.get("sentiment"),
            "topics": topics,
            "topic_confidence": d.get("topic_confidence"),
            "keywords": d.get("keywords"),
            "summary": d.get("summary"),
            "nlp_meta": meta,
            "keyword_in_text_rate": round(kw_rate, 4),
            "topic_in_taxonomy": topic in TOPIC_SET,
            "ok": True,
            "wall_ms": round(wall_ms, 1),
            "_usage": usage,
            "_lat": lat,
            "_kw_rate": kw_rate,
            "_topic_ok": topic in TOPIC_SET,
            "_degraded": bool(meta.get("degraded")),
            "_chunked": bool(meta.get("chunked")),
            "_skipped": bool(meta.get("skipped")),
            "_has_summary": bool((d.get("summary") or "").strip()),
        }

    rows: List[Dict[str, Any]] = []
    parse_ok = 0
    topic_ok = 0
    kw_rates: List[float] = []
    latencies: List[float] = []
    sync_latencies: List[float] = []
    degraded = 0
    with_summary = 0
    usage_tot = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "reasoning_tokens": 0,
        "calls_ok": 0,
        "calls_fail": 0,
    }
    t_wall0 = time.perf_counter()
    workers = max(1, int(concurrency))
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_enrich_one, s): s for s in samples}
        for fut in as_completed(futs):
            row = fut.result()
            usage = row.pop("_usage", {}) or {}
            for k in usage_tot:
                usage_tot[k] += int(usage.get(k) or 0)
            if row.get("ok"):
                parse_ok += 1
                if row.pop("_topic_ok", False):
                    topic_ok += 1
                kw_rates.append(float(row.pop("_kw_rate") or 0))
                lat = float(row.pop("_lat") or row.get("wall_ms") or 0)
                latencies.append(lat)
                if not row.pop("_chunked", False) and not row.pop("_skipped", False):
                    sync_latencies.append(lat)
                if row.pop("_degraded", False):
                    degraded += 1
                if row.pop("_has_summary", False):
                    with_summary += 1
            else:
                row.pop("_lat", None)
                row.pop("_kw_rate", None)
                row.pop("_topic_ok", None)
                row.pop("_degraded", None)
                row.pop("_chunked", None)
                row.pop("_skipped", None)
                row.pop("_has_summary", None)
            rows.append(row)
            done += 1
            if done % 25 == 0:
                logging.getLogger("ai.enrichment").info(
                    "[COMPARE] model=%s progress=%s/%s concurrency=%s",
                    model,
                    done,
                    len(samples),
                    workers,
                )

    # Stable order matching fixture
    by_id = {r.get("id"): r for r in rows}
    rows = [by_id.get(s.get("id"), {"id": s.get("id"), "ok": False}) for s in samples]

    wall_s = time.perf_counter() - t_wall0
    n = len(samples) or 1
    enrich_cost = _cost_usd(model, usage_tot["prompt_tokens"], usage_tot["completion_tokens"])

    enrich_report = {
        "model": model,
        "n": len(samples),
        "concurrency": workers,
        "parse_success_rate": round(parse_ok / n, 4),
        "topic_in_taxonomy_rate": round(topic_ok / n, 4),
        "keyword_in_text_rate_mean": round(statistics.mean(kw_rates), 4) if kw_rates else None,
        "latency_ms_mean": round(statistics.mean(latencies), 1) if latencies else None,
        "latency_ms_p95_sync": round(_p95(sync_latencies), 1) if sync_latencies else None,
        "latency_ms_median": round(statistics.median(latencies), 1) if latencies else None,
        "wall_seconds_total": round(wall_s, 1),
        "degraded_rate": round(degraded / n, 4),
        "rows_with_summary": with_summary,
        "usage": usage_tot,
        "enrich_cost_usd": round(enrich_cost, 6),
        "price_per_1m": MODEL_PRICES.get(model),
        "rows": rows,
    }

    slug = model.replace("/", "_")
    enrich_path = out_dir / f"compare_enrich_{slug}.json"
    enrich_path.write_text(json.dumps(enrich_report, ensure_ascii=False, indent=2), encoding="utf-8")

    judge_report = None
    if judge:
        # Exclude full text from judge payload storage duplication handled in run_judge
        texts = {r["id"]: r["text"] for r in rows if r.get("ok") and r.get("text")}
        # strip heavy text from rows copy for judge input file shape
        slim = dict(enrich_report)
        slim_rows = []
        for r in rows:
            rr = dict(r)
            rr.pop("text", None)
            slim_rows.append(rr)
        slim["rows"] = slim_rows
        judge_path = out_dir / f"compare_judge_{slug}.json"
        judge_report = run_judge(
            slim,
            concurrency=5,
            fixture_texts=texts,
            out_path=judge_path,
        )

    return {
        "enrich": enrich_report,
        "judge": judge_report,
        "enrich_path": str(enrich_path),
    }


def build_table(results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    table_rows = []
    for model, payload in results.items():
        e = payload["enrich"]
        j = payload.get("judge") or {}
        table_rows.append(
            {
                "model": model,
                "luna_overall": j.get("mean_overall"),
                "luna_sentiment": (j.get("mean_by_task") or {}).get("sentiment"),
                "luna_topic": (j.get("mean_by_task") or {}).get("topic"),
                "luna_keywords": (j.get("mean_by_task") or {}).get("keywords"),
                "luna_summary": (j.get("mean_by_task") or {}).get("summary"),
                "judge_n_ok": j.get("n_ok"),
                "parse_success_rate": e.get("parse_success_rate"),
                "topic_in_taxonomy_rate": e.get("topic_in_taxonomy_rate"),
                "keyword_in_text_rate_mean": e.get("keyword_in_text_rate_mean"),
                "degraded_rate": e.get("degraded_rate"),
                "rows_with_summary": e.get("rows_with_summary"),
                "latency_ms_mean": e.get("latency_ms_mean"),
                "latency_ms_median": e.get("latency_ms_median"),
                "latency_ms_p95_sync": e.get("latency_ms_p95_sync"),
                "wall_seconds_total": e.get("wall_seconds_total"),
                "prompt_tokens": (e.get("usage") or {}).get("prompt_tokens"),
                "completion_tokens": (e.get("usage") or {}).get("completion_tokens"),
                "reasoning_tokens": (e.get("usage") or {}).get("reasoning_tokens"),
                "enrich_cost_usd": e.get("enrich_cost_usd"),
                "price_in_per_1m": (e.get("price_per_1m") or {}).get("input"),
                "price_out_per_1m": (e.get("price_per_1m") or {}).get("output"),
            }
        )
    return {
        "pricing_note": (
            "Enrichment API cost only (Call A+B). Luna judge cost excluded. "
            "Prices: gpt-4o-mini $0.15/$0.60, gpt-5-nano $0.05/$0.40 per 1M in/out "
            "(OpenAI model docs, Aug 2026)."
        ),
        "rows": table_rows,
    }


def main(argv: List[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default="gpt-4o-mini,gpt-5-nano")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--timeout-ms", type=int, default=15000)
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args(argv)

    from ai.enrichment.eval.sample_from_mongo import load_fixture

    root = Path(__file__).resolve().parent
    out_dir = root / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    fixture = load_fixture(root / "fixtures" / "mongo_sample_200.json")

    results: Dict[str, Dict[str, Any]] = {}
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        logging.info("[COMPARE] ===== starting model=%s =====", model)
        conc = args.concurrency
        if conc <= 1 and _is_openrouter_model(model):
            conc = 4  # free tier is slow; parallelize rows for wall time
        results[model] = run_model(
            model,
            fixture,
            out_dir=out_dir,
            judge=not args.skip_judge,
            limit=args.limit,
            timeout_ms=args.timeout_ms,
            concurrency=conc,
        )

    table = build_table(results)
    out = out_dir / "model_compare_table.json"
    out.write_text(json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")

    # Pretty markdown table
    headers = [
        "model",
        "luna_overall",
        "luna_sentiment",
        "luna_topic",
        "luna_keywords",
        "luna_summary",
        "latency_ms_mean",
        "latency_ms_p95_sync",
        "wall_seconds_total",
        "enrich_cost_usd",
        "degraded_rate",
        "parse_success_rate",
    ]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in table["rows"]:
        lines.append(
            "| "
            + " | ".join(str(row.get(h) if row.get(h) is not None else "") for h in headers)
            + " |"
        )
    md = table["pricing_note"] + "\n\n" + "\n".join(lines) + "\n"
    md_path = out_dir / "model_compare_table.md"
    md_path.write_text(md, encoding="utf-8")
    print(md)
    print(f"\nWrote {out} and {md_path}")
    return 0


if __name__ == "__main__":
    backend = Path(__file__).resolve().parents[3]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    raise SystemExit(main())
