#!/usr/bin/env python3
"""Send one typed influencer_discovery command to the crawler SQS queue."""
from __future__ import annotations

import argparse
import json
import re
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
        description="Trigger the Data-Crawler-Task influencer pipeline through SQS."
    )
    parser.add_argument("--field", required=True, help="Influencer discovery field.")
    parser.add_argument("--company-id", required=True, help="Stable company identity.")
    parser.add_argument("--company-name", required=True, help="Company display name.")
    parser.add_argument("--company-domain", required=True, help="Company DNS domain.")
    parser.add_argument("--company-summary", required=True, help="Company summary used for relevance.")
    parser.add_argument(
        "--related-terms",
        required=True,
        help="Comma-separated related discovery terms.",
    )
    parser.add_argument("--platform", choices=("x",), default="x")
    parser.add_argument("--limit", type=int, required=True, help="Profiles to rank (1-100).")
    parser.add_argument("--job-id", default=None, help="Optional idempotency key.")
    parser.add_argument("--resume", action="store_true", help="Resume unfinished durable profile work.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not 1 <= args.limit <= 100:
        raise SystemExit("--limit must be between 1 and 100")
    field = args.field.strip()
    if not field:
        raise SystemExit("--field cannot be empty")
    company_id = args.company_id.strip()
    company_name = args.company_name.strip()
    company_domain = args.company_domain.strip().lower()
    company_summary = args.company_summary.strip()
    if not company_id:
        raise SystemExit("--company-id cannot be empty")
    if not company_name:
        raise SystemExit("--company-name cannot be empty")
    if not re.fullmatch(r"[a-z0-9.-]+", company_domain):
        raise SystemExit("--company-domain must be a valid domain")
    if not company_summary:
        raise SystemExit("--company-summary cannot be empty")
    related_terms = [term.strip() for term in args.related_terms.split(",") if term.strip()]
    if not related_terms:
        raise SystemExit("--related-terms must contain at least one term")
    _load_backend()
    from publishers.command_sqs import build_crawl_command, publish_crawl_command

    job_id = args.job_id or str(uuid.uuid4())
    input_data = {
        "company_id": company_id,
        "company_name": company_name,
        "company_domain": company_domain,
        "company_summary": company_summary,
        "field": field,
        "related_terms": related_terms,
        "platform": args.platform,
        "limit": args.limit,
        "resume": args.resume,
    }
    publish_crawl_command(
        job_id=job_id,
        task_type="influencer_discovery",
        input_data=input_data,
    )
    print(json.dumps(build_crawl_command(
        job_id=job_id, task_type="influencer_discovery", input_data=input_data
    ), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
