"""Token pricing (V1.1).

`runs.cost` has existed since Alembic 0001 but nothing ever wrote it, so every run reported a
cost of 0. This module is what makes that column carry real numbers.

Prices are USD per 1K tokens, `(input, output)`. The built-in table covers the models this
deployment actually uses; anything else must come from `Settings.model_prices`, because a
wrong hard-coded price is worse than a visibly missing one.
"""

import logging

logger = logging.getLogger(__name__)

# USD per 1K tokens: model -> (prompt, completion).
DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "deepseek-chat": (0.00027, 0.0011),
    "deepseek-reasoner": (0.00055, 0.00219),
    "gpt-4o": (0.0025, 0.01),
    "gpt-4o-mini": (0.00015, 0.0006),
    "claude-sonnet-5": (0.003, 0.015),
    "claude-opus-4-8": (0.015, 0.075),
    "claude-haiku-4-5-20251001": (0.0008, 0.004),
}

_warned: set[str] = set()


def resolve_prices(overrides: dict[str, list[float]] | None = None) -> dict[str, tuple[float, float]]:
    """Merge configured overrides over the built-in table."""
    prices = dict(DEFAULT_PRICES)
    for model, pair in (overrides or {}).items():
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            prices[model] = (float(pair[0]), float(pair[1]))
        else:
            logger.warning("ignoring malformed price for %s: %r (want [input, output])", model, pair)
    return prices


def estimate_cost(
    model: str | None,
    usage: dict | None,
    *,
    overrides: dict[str, list[float]] | None = None,
) -> float:
    """Estimate a call's cost in USD. Unknown model or missing usage → 0.0.

    Never raises: cost accounting is reporting, and a pricing gap must not fail a run.
    """
    if not model or not usage:
        return 0.0
    prices = resolve_prices(overrides)
    pair = prices.get(model)
    if pair is None:
        # Try a prefix match so versioned ids ("gpt-4o-2024-08-06") reuse the base price.
        for known, known_pair in prices.items():
            if model.startswith(known):
                pair = known_pair
                break
    if pair is None:
        if model not in _warned:
            _warned.add(model)
            logger.warning("no price for model %s; run cost will be reported as 0", model)
        return 0.0

    prompt_price, completion_price = pair
    prompt_tokens = usage.get("prompt_tokens", 0) or 0
    completion_tokens = usage.get("completion_tokens", 0) or 0
    return round(prompt_tokens / 1000 * prompt_price + completion_tokens / 1000 * completion_price, 6)


__all__ = ["DEFAULT_PRICES", "estimate_cost", "resolve_prices"]
