"""Command line interface. Day 6: `classify`. (`triage` and `batch` arrive on Day 8.)

python -m src.cli classify path/to/ticket.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from src.agents.classifier import ClassificationError, classify
from src.config import Settings, get_settings
from src.llm import AnthropicLLM, LLMClient, LLMError
from src.schemas import Ticket


async def run_classify(path: str, settings: Settings, llm: LLMClient | None = None) -> int:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        ticket = Ticket.model_validate(raw)
    except OSError as exc:
        print(f"Cannot read {path}: {exc.strerror}", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, ValidationError) as exc:
        print(f"{path} is not a valid ticket: {exc}", file=sys.stderr)
        return 2

    try:
        client = llm or AnthropicLLM(settings)
        classification, usage, attempts = await classify(client, ticket, None, settings)
    except ClassificationError as exc:
        print(f"CLASSIFICATION FAILED: {exc}", file=sys.stderr)
        return 1
    except LLMError as exc:
        print(f"MODEL ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(classification.model_dump_json(indent=2))
    print(f"\nattempts: {attempts}")
    print(f"tokens in/out: {usage.input_tokens}/{usage.output_tokens}")
    print(f"cache read/write: {usage.cache_read_tokens}/{usage.cache_write_tokens}")
    print(f"cost: ${usage.cost_usd:.4f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="triagedesk")
    sub = parser.add_subparsers(dest="command", required=True)
    p_classify = sub.add_parser("classify", help="classify one ticket JSON file (calls the API)")
    p_classify.add_argument("path", help="ticket JSON file")
    args = parser.parse_args(argv)
    if args.command == "classify":
        return asyncio.run(run_classify(args.path, get_settings()))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
