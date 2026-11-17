"""Token-to-dollar maths (blueprint Day 5, step 2).

Prices come from data/pricing.json (USD per million tokens). A model that is missing from the
file costs 0.0 and prints one warning to stderr, so a typo in a model id is visible but never
crashes a triage run.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping

from src.data import load_pricing
from src.schemas import Usage

_warned: set[str] = set()


def compute_cost(
    model: str, usage: Usage, pricing: Mapping[str, Mapping[str, float]] | None = None
) -> float:
    """Dollar cost of `usage` for `model`. Only the token counts of `usage` are read.

    The API reports input_tokens separately from cache reads and cache writes, so the four
    token kinds are simply priced and added (no subtraction).
    """
    table = load_pricing() if pricing is None else pricing
    price = table.get(model)
    if price is None:
        if model not in _warned:
            _warned.add(model)
            print(f"warning: no pricing for model {model!r}; cost reported as 0.0", file=sys.stderr)
        return 0.0
    return (
        usage.input_tokens * price["input_per_mtok"]
        + usage.output_tokens * price["output_per_mtok"]
        + usage.cache_read_tokens * price["cache_read_per_mtok"]
        + usage.cache_write_tokens * price["cache_write_per_mtok"]
    ) / 1_000_000
