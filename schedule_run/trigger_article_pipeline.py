#!/usr/bin/env python3
"""Send one typed content_crawl command to the crawler SQS queue."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Sequence


def _load_backend() -> None:
    backend_dir = Path(__file__).resolve().parents[1] / "Backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trigger the Data-Crawler-Task article pipeline through SQS."
    )
    parser.add_argument("--query", required=True, help="Content search query.")
    parser.add_argument(
        "--source",
        default="all",
        choices=("x", "reddit", "youtube", "duckduckgo", "news", "all"),
        help="Crawler source category (default: all).",
    )
    parser.add_argument(
        "--time-delta",
        default=None,
        help="hour, day, week, month, year, or a positive day count.",
    )
    parser.add_argument("--limit", type=int, default=20, help="Items per source (1-100).")
    parser.add_argument("--job-id", default=None, help="Optional idempotency key.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not 1 <= args.limit <= 100:
        raise SystemExit("--limit must be between 1 and 100")
    _load_backend()
    from publishers.command_sqs import build_crawl_command, publish_crawl_command

    job_id = args.job_id or str(uuid.uuid4())
    input_data = {
        "query": args.query.strip(),
        "source": args.source,
        "time_delta": args.time_delta,
        "limit": args.limit,
    }
    if not input_data["query"]:
        raise SystemExit("--query cannot be empty")
    publish_crawl_command(
        job_id=job_id,
        task_type="content_crawl",
        input_data=input_data,
    )
    print(json.dumps(build_crawl_command(
        job_id=job_id, task_type="content_crawl", input_data=input_data
    ), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
