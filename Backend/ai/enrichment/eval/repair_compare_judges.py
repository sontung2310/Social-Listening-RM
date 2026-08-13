"""Re-judge failed compare rows and rebuild a clean 200/200 accuracy table."""
from __future__ import annotations

import json
import logging
import statistics
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

from ai.enrichment.eval.judge import judge_one
from ai.enrichment.llm_client import LLMClient

logger = logging.getLogger("ai.enrichment")
REPORTS = Path(__file__).resolve().parent / "reports"


def _reaggregate(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    ok_rows = [j for j in results if j.get("ok")]
    overalls: List[float] = []
    task_means: Dict[str, List[float]] = {
        "sentiment": [],
        "topic": [],
        "keywords": [],
        "summary": [],
    }
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
                if part.get("score") is None:
                    continue
                task_means[task].append(float(part.get("score")))
            except (TypeError, ValueError):
                pass
        for tag in g.get("fail_tags") or []:
            fail_hist[str(tag)] = fail_hist.get(str(tag), 0) + 1

    worst = sorted(
        ok_rows,
        key=lambda j: float((j.get("judge") or {}).get("overall") or 0),
    )[:25]

    return {
        "n_judged": len(results),
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
        "results": results,
    }


def _well_counts(judge_report: Dict[str, Any]) -> Dict[str, Any]:
    results = [r for r in judge_report.get("results") or [] if r.get("ok")]
    n_judged = len(results)
    out: Dict[str, Any] = {"n_judged_ok": n_judged, "n_fail": judge_report.get("n_judged", 0) - n_judged}

    def scores(task: str):
        vals = []
        na = 0
        for r in results:
            part = (r.get("judge") or {}).get(task) or {}
            if task == "summary" and part.get("na"):
                na += 1
                continue
            if part.get("score") is None:
                continue
            try:
                vals.append(float(part["score"]))
            except (TypeError, ValueError):
                pass
        return vals, na

    for task in ("sentiment", "topic", "keywords", "summary", "overall"):
        if task == "overall":
            vals = []
            for r in results:
                try:
                    vals.append(float((r.get("judge") or {}).get("overall")))
                except (TypeError, ValueError):
                    pass
            na = 0
        else:
            vals, na = scores(task)
        denom = len(vals)
        ge4 = sum(1 for s in vals if s >= 4)
        exact5 = sum(1 for s in vals if round(s) == 5)
        out[task] = {
            "scored_rows": denom,
            "na_rows": na,
            "ge4": ge4,
            "exact5": exact5,
            "pct_ge4": round(100 * ge4 / denom, 1) if denom else None,
            "mean": round(statistics.mean(vals), 3) if vals else None,
            "score_dist": dict(sorted(Counter(int(round(s)) for s in vals).items())),
        }

    all_well = 0
    for r in results:
        g = r.get("judge") or {}
        ok_all = True
        for task in ("sentiment", "topic", "keywords"):
            part = g.get(task) or {}
            try:
                if float(part.get("score")) < 4:
                    ok_all = False
                    break
            except (TypeError, ValueError):
                ok_all = False
                break
        if ok_all:
            sp = g.get("summary") or {}
            if not sp.get("na"):
                try:
                    if float(sp.get("score")) < 4:
                        ok_all = False
                except (TypeError, ValueError):
                    ok_all = False
        if ok_all:
            all_well += 1
    out["all_tasks_ge4"] = all_well
    out["pct_all_tasks_ge4"] = round(100 * all_well / n_judged, 1) if n_judged else None
    return out


def repair_model(model: str) -> Dict[str, Any]:
    enrich_path = REPORTS / f"compare_enrich_{model.replace('/', '_')}.json"
    judge_path = REPORTS / f"compare_judge_{model.replace('/', '_')}.json"
    enrich = json.loads(enrich_path.read_text(encoding="utf-8"))
    judge = json.loads(judge_path.read_text(encoding="utf-8"))

    by_id = {r.get("id"): r for r in enrich.get("rows") or [] if r.get("ok")}
    results = list(judge.get("results") or [])
    fail_idxs = [i for i, r in enumerate(results) if not r.get("ok")]
    logger.info("[REPAIR] model=%s failed_judge=%s", model, len(fail_idxs))

    client = LLMClient()
    # Ensure Luna path does not inherit nano reasoning_effort
    client.judge_model = "gpt-5.6-luna"

    to_retry = []
    for i in fail_idxs:
        rid = results[i].get("id")
        row = by_id.get(rid)
        if not row:
            logger.warning("[REPAIR] missing enrich row id=%s", rid)
            continue
        to_retry.append((i, row))

    repaired = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(judge_one, client, row): idx for idx, row in to_retry}
        for fut in as_completed(futs):
            idx = futs[fut]
            repaired[idx] = fut.result()

    still_fail = 0
    for idx, res in repaired.items():
        results[idx] = res
        if not res.get("ok"):
            still_fail += 1
            logger.warning(
                "[REPAIR] still fail id=%s err=%s",
                res.get("id"),
                (res.get("error") or "")[:160],
            )

    updated = _reaggregate(results)
    updated["model"] = model
    updated["repaired_attempted"] = len(to_retry)
    updated["repaired_still_fail"] = still_fail
    judge_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "[REPAIR] model=%s n_ok=%s/%s mean=%s",
        model,
        updated["n_ok"],
        updated["n_judged"],
        updated["mean_overall"],
    )
    return updated


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    models = ["gpt-4o-mini", "gpt-5-nano"]
    summaries = {}
    for model in models:
        updated = repair_model(model)
        summaries[model] = {
            "judge": {
                "n_judged": updated["n_judged"],
                "n_ok": updated["n_ok"],
                "mean_overall": updated["mean_overall"],
                "mean_by_task": updated["mean_by_task"],
                "fail_tag_histogram": updated["fail_tag_histogram"],
                "repaired_attempted": updated.get("repaired_attempted"),
                "repaired_still_fail": updated.get("repaired_still_fail"),
            },
            "well_counts": _well_counts(updated),
        }

    # Refresh markdown compare snippet for accuracy counts
    lines = [
        "# Model compare accuracy (after Luna re-judge repair)",
        "",
        "Denominator = successfully judged rows (target 200/200).",
        "Well = Luna score ≥ 4.",
        "",
    ]
    for model, payload in summaries.items():
        wc = payload["well_counts"]
        j = payload["judge"]
        lines.append(f"## {model}")
        lines.append("")
        lines.append(f"- Judged OK: **{j['n_ok']} / {j['n_judged']}** (still fail: {j.get('repaired_still_fail')})")
        lines.append(f"- Luna mean overall: **{j['mean_overall']}**")
        lines.append("")
        lines.append("| Task | Scored rows | Well (≥4) | Pct | Mean | Exact 5 |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
        for task in ("overall", "sentiment", "topic", "keywords", "summary"):
            d = wc[task]
            na = f" (NA={d['na_rows']})" if d.get("na_rows") else ""
            lines.append(
                f"| {task}{na} | {d['scored_rows']} | {d['ge4']} | {d['pct_ge4']}% | {d['mean']} | {d['exact5']} |"
            )
        lines.append(
            f"| all tasks ≥4 | {wc['n_judged_ok']} | {wc['all_tasks_ge4']} | {wc['pct_all_tasks_ge4']}% |  |  |"
        )
        lines.append("")

    out_md = REPORTS / "model_compare_accuracy_200.md"
    out_json = REPORTS / "model_compare_accuracy_200.json"
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_json.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_md.read_text(encoding="utf-8"))
    print(f"Wrote {out_md} and {out_json}")
    return 0


if __name__ == "__main__":
    backend = Path(__file__).resolve().parents[3]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    raise SystemExit(main())
