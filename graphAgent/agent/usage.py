"""Token usage tracking and cost estimation."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from config import ANTHROPIC_MODEL, load_defaults


def _empty_usage() -> dict[str, Any]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "llm_calls": 0,
        "estimated_cost_usd": 0.0,
    }


def extract_message_usage(message: AIMessage) -> dict[str, int]:
    input_tokens = 0
    output_tokens = 0

    usage_meta = getattr(message, "usage_metadata", None)
    if usage_meta:
        input_tokens = int(usage_meta.get("input_tokens") or 0)
        output_tokens = int(usage_meta.get("output_tokens") or 0)

    if input_tokens == 0 and output_tokens == 0:
        response_meta = getattr(message, "response_metadata", None) or {}
        usage = response_meta.get("usage") or response_meta.get("token_usage") or {}
        input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def merge_usage(current: dict[str, Any] | None, delta: dict[str, int]) -> dict[str, Any]:
    base = dict(current or _empty_usage())
    base["input_tokens"] = int(base.get("input_tokens", 0)) + delta.get("input_tokens", 0)
    base["output_tokens"] = int(base.get("output_tokens", 0)) + delta.get("output_tokens", 0)
    base["total_tokens"] = int(base.get("total_tokens", 0)) + delta.get("total_tokens", 0)
    base["llm_calls"] = int(base.get("llm_calls", 0)) + 1
    base["estimated_cost_usd"] = estimate_cost_usd(
        base["input_tokens"],
        base["output_tokens"],
        ANTHROPIC_MODEL,
    )
    return base


def estimate_cost_usd(input_tokens: int, output_tokens: int, model: str) -> float:
    defaults = load_defaults()
    pricing = defaults.get("pricing", {})
    model_rates = pricing.get(model) or pricing.get("default") or {}
    input_rate = float(model_rates.get("input_per_million_usd", 3.0))
    output_rate = float(model_rates.get("output_per_million_usd", 15.0))
    cost = (input_tokens / 1_000_000 * input_rate) + (output_tokens / 1_000_000 * output_rate)
    return round(cost, 6)


def format_usage_summary(usage: dict[str, Any] | None) -> str:
    usage = usage or _empty_usage()
    return (
        f"Tokens: {usage.get('input_tokens', 0):,} in + "
        f"{usage.get('output_tokens', 0):,} out = "
        f"{usage.get('total_tokens', 0):,} total | "
        f"LLM calls: {usage.get('llm_calls', 0)} | "
        f"Est. cost: ${usage.get('estimated_cost_usd', 0.0):.4f} USD"
    )
