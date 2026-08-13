"""Merge prior OpenAI compare metrics with a new openrouter/free run into one table."""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


def _well_counts(judge_report: Dict[str, Any]) -> Dict[str, Any]:
    results = [r for r in judge_report.get("results") or [] if r.get("ok")]
    n_judged = len(results)
    out: Dict[str, Any] = {
        "n_judged_ok": n_judged,
        "n_fail": judge_report.get("n_judged", 0) - n_judged,
    }

    def scores(task: str):
        vals: List[float] = []
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
        out[task] = {
            "scored_rows": denom,
            "na_rows": na,
            "ge4": ge4,
            "pct_ge4": round(100 * ge4 / denom, 1) if denom else None,
            "mean": round(statistics.mean(vals), 3) if vals else None,
        }
    return out


def _fmt_well(wc: Dict[str, Any], task: str) -> str:
    t = wc.get(task) or {}
    ge4 = t.get("ge4")
    denom = t.get("scored_rows")
    pct = t.get("pct_ge4")
    if ge4 is None or denom is None:
        return "—"
    return f"{ge4} / {denom} ({pct}%)"


def _load_model(reports: Path, slug: str) -> Dict[str, Any]:
    enrich = json.loads((reports / f"compare_enrich_{slug}.json").read_text(encoding="utf-8"))
    judge = json.loads((reports / f"compare_judge_{slug}.json").read_text(encoding="utf-8"))
    # Prefer repaired accuracy file if present for openai models
    return {"enrich": enrich, "judge": judge, "well": _well_counts(judge)}


def main() -> int:
    reports = Path(__file__).resolve().parent / "reports"
    models = [
        ("gpt-4o-mini", "gpt-4o-mini"),
        ("gpt-5-nano", "gpt-5-nano"),
        ("openrouter/free", "openrouter_free"),
    ]
    cols: Dict[str, Dict[str, Any]] = {}
    for label, slug in models:
        cols[label] = _load_model(reports, slug)

    # Override OpenAI well counts from repaired accuracy file when available
    acc_path = reports / "model_compare_accuracy_200.json"
    if acc_path.exists():
        acc = json.loads(acc_path.read_text(encoding="utf-8"))
        for label in ("gpt-4o-mini", "gpt-5-nano"):
            if label in acc and acc[label].get("well_counts"):
                cols[label]["well"] = acc[label]["well_counts"]

    headers = ["Task"] + [m[0] + " well" for m in models]
    tasks = ["Overall", "Sentiment", "Topic", "Keywords", "Summary"]
    task_keys = ["overall", "sentiment", "topic", "keywords", "summary"]

    lines = [
        "# Model compare (200-row fixture)",
        "",
        "Luna judge well = score ≥ 4 (scale 1–5). Summary denominator excludes rows marked NA (short text, no summary expected).",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for name, key in zip(tasks, task_keys):
        row = [name] + [_fmt_well(cols[m[0]]["well"], key) for m in models]
        lines.append("| " + " | ".join(row) + " |")

    lines += [
        "",
        "| Metric | " + " | ".join(m[0] for m in models) + " |",
        "| --- | " + " | ".join(["---"] * len(models)) + " |",
    ]
    metric_rows = [
        (
            "Mean latency / request",
            lambda e: f"{e.get('latency_ms_mean')} ms" if e.get("latency_ms_mean") is not None else "—",
        ),
        (
            "Total wall time",
            lambda e: f"{e.get('wall_seconds_total')} s" if e.get("wall_seconds_total") is not None else "—",
        ),
        (
            "USD for 200 rows",
            lambda e: f"${e.get('enrich_cost_usd'):.4f}" if e.get("enrich_cost_usd") is not None else "—",
        ),
        (
            "Est. per 1,000 docs",
            lambda e: (
                f"${(e.get('enrich_cost_usd') or 0) * 5:.4f}"
                if e.get("enrich_cost_usd") is not None
                else "—"
            ),
        ),
        (
            "Degraded rate",
            lambda e: f"{(e.get('degraded_rate') or 0) * 100:.1f}%",
        ),
    ]
    for label, fn in metric_rows:
        row = [label] + [fn(cols[m[0]]["enrich"]) for m in models]
        lines.append("| " + " | ".join(row) + " |")

    md = "\n".join(lines) + "\n"
    out_md = reports / "model_compare_final.md"
    out_md.write_text(md, encoding="utf-8")

    payload = {
        "models": {
            label: {
                "well": cols[label]["well"],
                "latency_ms_mean": cols[label]["enrich"].get("latency_ms_mean"),
                "wall_seconds_total": cols[label]["enrich"].get("wall_seconds_total"),
                "enrich_cost_usd": cols[label]["enrich"].get("enrich_cost_usd"),
                "cost_per_1000_usd": round((cols[label]["enrich"].get("enrich_cost_usd") or 0) * 5, 6),
                "degraded_rate": cols[label]["enrich"].get("degraded_rate"),
            }
            for label, _ in models
        },
        "notes": [
            "Summary denominators differ because Luna sets summary.na=true for short texts; only scored rows count.",
            "openrouter/free evaluated with NLP_OPENROUTER_ONLY=1 (no OpenAI paid failover). Cost listed as $0.",
            "Enrichment cost only; Luna judge excluded.",
        ],
    }
    out_json = reports / "model_compare_final.json"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(md)
    print(f"Wrote {out_md} and {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
