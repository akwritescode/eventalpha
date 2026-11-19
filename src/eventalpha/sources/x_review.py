"""Operator entry point for manually reviewed discovery links; never fetches X content."""

import argparse
import os
from datetime import datetime

from eventalpha.db import make_engine
from eventalpha.sources.x import record_lead, verify_lead


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record")
    record.add_argument("--post-id", required=True)
    record.add_argument("--ticker", required=True)
    record.add_argument("--paraphrase", required=True, help="Your own brief description, never copied post text")
    record.add_argument("--published-at", required=True, type=datetime.fromisoformat)
    verify = commands.add_parser("verify")
    verify.add_argument("--post-id", required=True)
    verify.add_argument("--source", required=True)
    verify.add_argument("--source-id", required=True)
    verify.add_argument("--supporting-passage", required=True)
    args = vars(parser.parse_args())
    command = args.pop("command")
    url = os.environ.get("EVENTALPHA_DATABASE_URL")
    if not url:
        parser.error("EVENTALPHA_DATABASE_URL is required")
    engine = make_engine(url)
    try:
        if command == "record":
            record_lead(engine, **args)
        elif not verify_lead(engine, **args):
            parser.exit(1, "Review was not recorded: check the original, ticker and existing decision.\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
