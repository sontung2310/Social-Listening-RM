"""Synthesize prompt-improvement guidance via OpenAI Luna."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai.enrichment.llm_client import LLMClient
from ai.enrichment.logging_util import log_step
from ai.enrichment.prompts import classify_v1, extract_v1
from ai.enrichment.validate import extract_json_object

logger = logging.getLogger("ai.enrichment")


def synthesize(
    judge_report: Dict[str, Any],
    *,
    round_n: int = 0,
    out_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    client = LLMClient()
    summary = {
        "mean_overall": judge_report.get("mean_overall"),
        "mean_by_task": judge_report.get("mean_by_task"),
        "fail_tag_histogram": judge_report.get("fail_tag_histogram"),
        "worst_samples": [
            {
                "id": w.get("id"),
                "source": w.get("source"),
                "overall": w.get("overall"),
                "fail_tags": w.get("fail_tags"),
                "rationales": {
                    k: ((w.get("judge") or {}).get(k) or {}).get("rationale")
                    for k in ("sentiment", "topic", "keywords", "summary")
                },
            }
            for w in (judge_report.get("worst_samples") or [])[:12]
        ],
    }
    current_prompts = {
        "classify_system_excerpt": classify_v1.system_prompt()[:1800],
        "extract_system_excerpt": extract_v1.system_prompt(summarize=True)[:1200],
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You improve prompts for a social-listening enrichment pipeline.\n"
                "There are two calls:\n"
                "- Call A (classify): sentiment + single topic from a fixed taxonomy\n"
                "- Call B (extract): keywords for word cloud + optional summary\n\n"
                "Given judge metrics and worst failures, output actionable guidance.\n"
                "Return JSON only with keys:\n"
                "{\n"
                '  "classify_edits": ["..."],\n'
                '  "extract_edits": ["..."],\n'
                '  "new_few_shots": [{"call":"A|B","user":"...","assistant_json":"..."}],\n'
                '  "taxonomy_disambiguation": ["..."],\n'
                '  "do_not_change": ["..."],\n'
                '  "priority": ["highest impact change first"],\n'
                '  "markdown_guidance": "full markdown guidance for engineers"\n'
                "}"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"judge_summary": summary, "current_prompts": current_prompts},
                ensure_ascii=False,
            ),
        },
    ]
    log_step("GUIDANCE_REQ", round=round_n)
    # Luna/GPT-5 may spend completion budget on reasoning; request a large cap.
    resp = client.judge_chat(messages, max_tokens=8000)
    obj = extract_json_object(resp.content) if resp.ok else None
    if not obj and resp.ok and (resp.content or "").strip():
        obj = {
            "markdown_guidance": resp.content,
            "classify_edits": [],
            "extract_edits": [],
        }
    if not obj:
        # Fallback markdown-only with long timeout
        md_messages = [
            {
                "role": "system",
                "content": (
                    "You improve prompts for Call A (sentiment+topic) and Call B "
                    "(keywords+summary). Write markdown guidance with sections: "
                    "Classify edits, Extract edits, Taxonomy disambiguation, "
                    "New few-shots, Do not change, Priority."
                ),
            },
            messages[1],
        ]
        prev = client.timeout_s
        client.timeout_s = max(prev, 90.0)
        try:
            resp2 = client.chat(
                md_messages,
                temperature=0.2,
                max_tokens=8000,
                json_mode=False,
                event_prefix="JUDGE",
                force_provider="openai",
                force_model=client.judge_model,
            )
        finally:
            client.timeout_s = prev
        if resp2.ok and resp2.content:
            obj = extract_json_object(resp2.content) or {
                "markdown_guidance": resp2.content,
                "classify_edits": [],
                "extract_edits": [],
                "priority": [],
                "taxonomy_disambiguation": [],
                "do_not_change": [],
                "new_few_shots": [],
            }
        else:
            obj = {
                "error": resp.error or (resp2.error if resp2 else "parse_fail"),
                "raw": ((resp.content or "") or (resp2.content if resp2 else ""))[:2000],
                "markdown_guidance": (resp.content or "")
                or (resp2.content if resp2 else ""),
            }
    log_step("GUIDANCE_RES", round=round_n, ok=bool(obj.get("markdown_guidance")))

    out_dir = out_dir or (Path(__file__).resolve().parent / "reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"guidance_round_{round_n}.json"
    md_path = out_dir / f"guidance_round_{round_n}.md"
    json_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    md = obj.get("markdown_guidance") or json.dumps(obj, indent=2)
    md_path.write_text(str(md), encoding="utf-8")
    logger.info("[GUIDANCE] wrote %s and %s", json_path, md_path)
    return obj


def main(argv: List[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge", type=Path, required=True)
    parser.add_argument("--round", type=int, default=0)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    report = json.loads(args.judge.read_text(encoding="utf-8"))
    synthesize(report, round_n=args.round, out_dir=args.out_dir)
    return 0


if __name__ == "__main__":
    backend = Path(__file__).resolve().parents[3]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    raise SystemExit(main())
