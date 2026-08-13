"""python -m workers [--once]"""
from __future__ import annotations

import argparse
import logging
import sys

import config  # noqa: F401 — path + env
from workers.consumer import run_forever, run_once


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pace-Unit AI worker (simulated SQS)")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process pending fixture messages once and exit",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    if args.once:
        n = run_once()
        logging.getLogger(__name__).info("Done — processed %s message(s)", n)
        return 0 if n >= 0 else 1

    run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
