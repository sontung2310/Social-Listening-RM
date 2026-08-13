"""Orchestrate sample → enrich → judge → guidance (one or more rounds)."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List

logger = logging.getLogger("ai.enrichment")


def main(argv: List[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(description="Enrichment eval + Luna judge loop")
    parser.add_argument("--round", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None, help="Limit samples (debug)")
    parser.add_argument("--skip-sample", action="store_true")
    parser.add_argument("--skip-enrich", action="store_true")
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--skip-guidance", action="store_true")
    parser.add_argument("--judge-concurrency", type=int, default=5)
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    fixture_path = root / "fixtures" / "mongo_sample_200.json"
    enrich_path = reports / f"enrichment_round_{args.round}.json"
    judge_path = reports / f"judge_round_{args.round}.json"

    if not args.skip_sample and not fixture_path.exists():
        from ai.enrichment.eval.sample_from_mongo import build_sample, save_fixture

        data = build_sample()
        save_fixture(data, fixture_path)
    elif not fixture_path.exists():
        raise SystemExit(f"Missing fixture {fixture_path}; run without --skip-sample")

    from ai.enrichment.eval.sample_from_mongo import load_fixture

    fixture = load_fixture(fixture_path)

    if not args.skip_enrich:
        from ai.enrichment.eval.run import run_enrichment_eval

        run_enrichment_eval(fixture, limit=args.limit, out_path=enrich_path)
    else:
        if not enrich_path.exists():
            raise SystemExit(f"Missing {enrich_path}")

    if not args.skip_judge:
        from ai.enrichment.eval.judge import run_judge

        enrichment = json.loads(enrich_path.read_text(encoding="utf-8"))
        texts = {s["id"]: s["text"] for s in fixture.get("samples") or []}
        run_judge(
            enrichment,
            concurrency=args.judge_concurrency,
            limit=args.limit,
            fixture_texts=texts,
            out_path=judge_path,
        )

    if not args.skip_guidance:
        if not judge_path.exists():
            raise SystemExit(f"Missing {judge_path}; run judge before guidance")
        from ai.enrichment.eval.synthesize_guidance import synthesize

        judge = json.loads(judge_path.read_text(encoding="utf-8"))
        synthesize(judge, round_n=args.round, out_dir=reports)

    logger.info("[LOOP] round=%s complete", args.round)
    return 0


if __name__ == "__main__":
    backend = Path(__file__).resolve().parents[3]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    raise SystemExit(main())
