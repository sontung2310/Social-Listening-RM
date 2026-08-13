"""OpenAI gpt-5.6-luna AI-as-a-judge for enrichment outputs."""
from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai.enrichment.llm_client import LLMClient
from ai.enrichment.logging_util import log_step, preview
from ai.enrichment.taxonomy import taxonomy_prompt_block
from ai.enrichment.validate import extract_json_object

logger = logging.getLogger("ai.enrichment")


def _judge_system() -> str:
    return f"""You are an expert evaluator for a social-listening NLP pipeline.
Score the model's enrichment of the given text. Be strict but fair.

Taxonomy (topic must be one of these):
{taxonomy_prompt_block()}

Rubric (integer 1–5 each):
- sentiment: correct polarity for the text
- topic: best single label from taxonomy
- keywords: useful for a word cloud; terms should appear in text; central concepts
- summary: faithful ≤2 sentences when present; if summary is empty and text is short, set na=true and score=5

Return JSON only:
{{"sentiment":{{"score":1,"rationale":"..."}},"topic":{{"score":1,"rationale":"..."}},"keywords":{{"score":1,"rationale":"..."}},"summary":{{"score":1,"rationale":"...","na":false}},"overall":1,"fail_tags":["topic_wrong"]}}

fail_tags examples: topic_wrong, keyword_not_in_text, keyword_noise, summary_hallucination, sentiment_miss, empty_keywords
"""


def judge_one(client: LLMClient, row: Dict[str, Any]) -> Dict[str, Any]:
    text = row.get("text_preview") or ""
    # prefer full text if present
    full = row.get("text")
    if full:
        text = full
    payload = {
        "source": row.get("source"),
        "content_type": row.get("content_type"),
        "text": text[:4000],
        "enrichment": {
            "sentiment": row.get("sentiment"),
            "topics": row.get("topics"),
            "keywords": row.get("keywords"),
            "summary": row.get("summary"),
        },
    }
    messages = [
        {"role": "system", "content": _judge_system()},
        {
            "role": "user",
            "content": "Evaluate this enrichment:\n" + json.dumps(payload, ensure_ascii=False),
        },
    ]
    log_step("JUDGE_REQ", id=row.get("id"), preview=preview(text, 120))
    # Luna may use reasoning tokens; give enough completion budget to still emit JSON.
    resp = client.judge_chat(messages, max_tokens=2048)
    obj = extract_json_object(resp.content) if resp.ok else None
    if not obj:
        log_step("JUDGE_RES", id=row.get("id"), error=resp.error or "parse_fail")
        return {
            "id": row.get("id"),
            "ok": False,
            "error": resp.error or "parse_fail",
            "raw": resp.content[:500] if resp.content else "",
        }
    log_step(
        "JUDGE_RES",
        id=row.get("id"),
        overall=obj.get("overall"),
        fail_tags=obj.get("fail_tags"),
    )
    return {
        "id": row.get("id"),
        "source": row.get("source"),
        "content_type": row.get("content_type"),
        "ok": True,
        "judge": obj,
        "provider": resp.provider,
        "model": resp.model,
        "latency_ms": resp.latency_ms,
    }


def run_judge(
    enrichment_report: Dict[str, Any],
    *,
    concurrency: int = 5,
    limit: Optional[int] = None,
    fixture_texts: Optional[Dict[str, str]] = None,
    out_path: Optional[Path] = None,
) -> Dict[str, Any]:
    rows = [r for r in enrichment_report.get("rows") or [] if r.get("ok")]
    if limit is not None:
        rows = rows[:limit]
    if fixture_texts:
        for r in rows:
            rid = r.get("id")
            if rid in fixture_texts:
                r["text"] = fixture_texts[rid]

    client = LLMClient()
    judged: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futs = {pool.submit(judge_one, client, row): row for row in rows}
        for fut in as_completed(futs):
            judged.append(fut.result())

    ok_rows = [j for j in judged if j.get("ok")]
    overalls = []
    task_means = {"sentiment": [], "topic": [], "keywords": [], "summary": []}
    fail_hist: Dict[str, int] = {}
    for j in ok_rows:
        g = j.get("judge") or {}
        try:
            overalls.append(float(g.get("overall") or 0))
        except (TypeError, ValueError):
            pass
        for task in task_means:
            part = g.get(task) or {}
            try:
                if task == "summary" and part.get("na"):
                    continue
                task_means[task].append(float(part.get("score") or 0))
            except (TypeError, ValueError):
                pass
        for tag in g.get("fail_tags") or []:
            fail_hist[str(tag)] = fail_hist.get(str(tag), 0) + 1

    # worst samples for guidance
    worst = sorted(
        ok_rows,
        key=lambda j: float((j.get("judge") or {}).get("overall") or 0),
    )[:25]

    report = {
        "n_judged": len(judged),
        "n_ok": len(ok_rows),
        "mean_overall": round(statistics.mean(overalls), 3) if overalls else None,
        "mean_by_task": {
            k: round(statistics.mean(v), 3) if v else None for k, v in task_means.items()
        },
        "fail_tag_histogram": dict(sorted(fail_hist.items(), key=lambda x: -x[1])),
        "worst_samples": [
            {
                "id": w.get("id"),
                "source": w.get("source"),
                "overall": (w.get("judge") or {}).get("overall"),
                "fail_tags": (w.get("judge") or {}).get("fail_tags"),
                "judge": w.get("judge"),
            }
            for w in worst
        ],
        "results": judged,
    }
    out_path = out_path or (
        Path(__file__).resolve().parent / "reports" / "judge_round_0.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "[JUDGE] wrote %s mean_overall=%s n_ok=%s",
        out_path,
        report["mean_overall"],
        report["n_ok"],
    )
    return report


def main(argv: List[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--enrichment", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args(argv)

    enrichment = json.loads(args.enrichment.read_text(encoding="utf-8"))
    texts = None
    if args.fixture:
        from ai.enrichment.eval.sample_from_mongo import load_fixture

        fix = load_fixture(args.fixture)
        texts = {s["id"]: s["text"] for s in fix.get("samples") or []}
    run_judge(
        enrichment,
        concurrency=args.concurrency,
        limit=args.limit,
        fixture_texts=texts,
        out_path=args.out,
    )
    return 0


if __name__ == "__main__":
    backend = Path(__file__).resolve().parents[3]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    raise SystemExit(main())
