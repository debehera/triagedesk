"""Run ONLY the classifier on the eval tickets and print accuracy (blueprint Day 6, step 8).

    python evals/classify_only.py                 # dev split (default)
    python evals/classify_only.py --ids EV-001,EV-013
    python evals/classify_only.py --include-holdout   # not before Day 13!

Calls the real API and costs money (cents). Tickets with `expected.category = null` are skipped.
The holdout split is refused unless you pass `--include-holdout`, so tuning prompts against it
by accident is impossible.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.classifier import ClassificationError, classify  # noqa: E402
from src.config import Settings, get_settings  # noqa: E402
from src.llm import LLMBudgetExhausted, LLMClient, LLMError  # noqa: E402
from src.schemas import Classification, Severity, Ticket, Usage  # noqa: E402

TICKETS_PATH = Path(__file__).resolve().parent / "tickets.jsonl"
LOW_CONFIDENCE = 0.7


@dataclass
class Row:
    id: str
    group: str
    expected_category: str
    acceptable: list[str]
    expected_severity: str
    got: Classification | None = None
    attempts: int = 0
    usage: Usage = field(default_factory=Usage)
    error: str | None = None

    @property
    def category_ok(self) -> bool:
        if self.got is None:
            return False
        return self.got.category.value in {self.expected_category, *self.acceptable}

    @property
    def severity_ok(self) -> bool:
        if self.got is None:
            return False
        return abs(self.got.severity.level - Severity(self.expected_severity).level) <= 1


def load_items(path: Path = TICKETS_PATH) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def select(
    items: list[dict], *, split: str, ids: set[str] | None, include_holdout: bool
) -> list[dict]:
    if split == "holdout" and not include_holdout:
        raise SystemExit("Refusing to run the holdout split before Day 13 (use --include-holdout).")
    chosen = [i for i in items if i["expected"]["category"] is not None]
    if ids is not None:
        chosen = [i for i in chosen if i["id"] in ids]
        if not include_holdout and any(i["split"] == "holdout" for i in chosen):
            raise SystemExit("Some ids are in the holdout split (use --include-holdout).")
    elif split != "all":
        chosen = [i for i in chosen if i["split"] == split]
    elif not include_holdout:
        raise SystemExit("Split 'all' includes holdout (use --include-holdout).")
    return chosen


async def run_one(llm: LLMClient, item: dict, settings: Settings) -> Row:
    expected = item["expected"]
    group = (item.get("tags") or ["-"])[0]
    row = Row(
        item["id"],
        group,
        expected["category"],
        expected["acceptable_categories"],
        expected["severity"],
    )
    ticket = Ticket.model_validate({k: item[k] for k in ("id", "subject", "body", "requester_id")})
    try:
        row.got, row.usage, row.attempts = await classify(llm, ticket, None, settings)
    except ClassificationError as exc:
        row.usage, row.attempts, row.error = exc.usage, exc.attempts, "ClassificationError"
    except LLMBudgetExhausted:
        raise
    except LLMError as exc:
        row.error = type(exc).__name__
    return row


async def run_all(
    llm: LLMClient, items: list[dict], settings: Settings, *, concurrency: int, max_cost: float
) -> list[Row]:
    gate = asyncio.Semaphore(concurrency)
    spent = 0.0

    async def guarded(item: dict) -> Row | None:
        nonlocal spent
        async with gate:
            if spent >= max_cost:
                return None  # cost cap reached: do not start new tickets
            row = await run_one(llm, item, settings)
            spent += row.usage.cost_usd
            return row

    results = await asyncio.gather(*(guarded(i) for i in items))
    return [r for r in results if r is not None]


def summarize(rows: list[Row]) -> dict:
    n = len(rows)
    low = [r for r in rows if r.got and r.got.confidence < LOW_CONFIDENCE]
    return {
        "tickets": n,
        "category_accuracy": sum(r.category_ok for r in rows) / n if n else 0.0,
        "severity_within_1": sum(r.severity_ok for r in rows) / n if n else 0.0,
        "low_confidence_ids": sorted(r.id for r in low),
        "errors": [r.id for r in rows if r.error],
        "cost_usd": sum(r.usage.cost_usd for r in rows),
        "attempts_over_1": [r.id for r in rows if r.attempts > 1],
    }


def format_rows(rows: list[Row]) -> str:
    lines = [f"{'id':7} {'group':10} {'expected':22} {'got':22} conf  flags"]
    for r in sorted(rows, key=lambda r: r.id):
        exp = f"{r.expected_category}/{r.expected_severity}"
        if r.got is None:
            lines.append(f"{r.id:7} {r.group:10} {exp:22} {'ERROR ' + str(r.error):22}")
            continue
        got = f"{r.got.category.value}/{r.got.severity.value}"
        mark = "ok " if r.category_ok and r.severity_ok else "MISMATCH"
        flags = ",".join(f.value for f in r.got.risk_flags) or "-"
        lines.append(
            f"{r.id:7} {r.group:10} {exp:22} {got:22} {r.got.confidence:.2f}  {flags}  {mark}"
        )
    return "\n".join(lines)


def format_summary(s: dict) -> str:
    return "\n".join(
        [
            "",
            f"Tickets run:          {s['tickets']}",
            f"Category accuracy:    {s['category_accuracy']:.0%}",
            f"Severity within +-1:  {s['severity_within_1']:.0%}",
            f"Low confidence (<{LOW_CONFIDENCE}): {', '.join(s['low_confidence_ids']) or 'none'}",
            f"Needed a retry:       {', '.join(s['attempts_over_1']) or 'none'}",
            f"Errors:               {', '.join(s['errors']) or 'none'}",
            f"Total cost:           ${s['cost_usd']:.4f}",
        ]
    )


async def main_async(args: argparse.Namespace) -> int:
    from src.llm import AnthropicLLM

    settings = get_settings()
    ids = set(args.ids.split(",")) if args.ids else None
    items = select(load_items(), split=args.split, ids=ids, include_holdout=args.include_holdout)
    if not items:
        print("No tickets selected.")
        return 2
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY is not set (see .env.example).")
        return 2
    llm = AnthropicLLM(settings)
    print(f"Classifier model: {settings.model_classifier}; running {len(items)} tickets...")
    try:
        rows = await run_all(
            llm, items, settings, concurrency=args.concurrency, max_cost=args.max_cost
        )
    except LLMBudgetExhausted:
        print("API spend limit reached. Stopping.")
        return 1
    print(format_rows(rows))
    print(format_summary(summarize(rows)))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--split", default="dev", choices=["dev", "holdout", "all"])
    parser.add_argument("--ids", help="comma-separated ticket ids, e.g. EV-001,EV-013")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--max-cost", type=float, default=0.50, help="stop starting tickets (USD)")
    parser.add_argument("--include-holdout", action="store_true", help="NOT before Day 13")
    return asyncio.run(main_async(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
