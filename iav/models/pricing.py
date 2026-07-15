"""Cost estimation from Gemini API token usage.

Token counts come straight from usage_metadata on each response — real,
not estimated. Dollar costs are computed from those counts against the
rates in config.yaml's pricing table, which mixes confirmed and
unconfirmed rates (see the `verified` flag per model). Cloud Billing is
the source of truth for actual charges, not this module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class UsageInfo:
    prompt_tokens: int = 0
    output_tokens: int = 0
    # Reasoning/"thinking" tokens (Gemini 2.5+ thinking models) and tool-use
    # tokens are separate buckets in Google's own schema, not part of
    # prompt/candidates -- billed as real tokens, so they must be counted,
    # not just carried in total_tokens for display.
    thoughts_tokens: int = 0
    tool_use_prompt_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0
    prompt_modality_breakdown: dict[str, int] = field(default_factory=dict)
    output_modality_breakdown: dict[str, int] = field(default_factory=dict)


@dataclass
class CostEstimate:
    model: str
    usd: float
    verified: bool
    input_usd: float = 0.0
    output_usd: float = 0.0
    breakdown: dict[str, float] = field(default_factory=dict)
    tokens: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "usd": round(self.usd, 6),
            "input_usd": round(self.input_usd, 6),
            "output_usd": round(self.output_usd, 6),
            "verified": self.verified,
            "breakdown": {k: round(v, 6) for k, v in self.breakdown.items()},
            "tokens": self.tokens,
            "notes": self.notes,
        }


def estimate_cost(
    *,
    model: str,
    usage: UsageInfo | None,
    pricing_table: dict[str, Any],
    output_images: int = 0,
    duration_seconds: float = 0.0,
    resolution: str | None = None,
    label: str = "",
) -> CostEstimate:
    models = (pricing_table or {}).get("models", {})
    entry = models.get(model)
    tokens = {
        "prompt": usage.prompt_tokens if usage else 0,
        "output": usage.output_tokens if usage else 0,
        "thoughts": usage.thoughts_tokens if usage else 0,
        "tool_use": usage.tool_use_prompt_tokens if usage else 0,
        "cached": usage.cached_tokens if usage else 0,
    }

    if entry is None:
        logger.warning("No pricing entry for model '%s' -- cost not estimated for this call", model)
        return CostEstimate(
            model=model,
            usd=0.0,
            verified=False,
            tokens=tokens,
            notes=[f"No pricing entry for '{model}' in config.yaml -> pricing.models."],
        )

    verified = bool(entry.get("verified", False))
    unit = entry.get("unit", "per_million_tokens")

    if unit == "per_second_video":
        return _estimate_video_cost(
            model=model, entry=entry, duration_seconds=duration_seconds, resolution=resolution, verified=verified
        )

    if unit == "per_image":
        return _estimate_flat_image_cost(model=model, entry=entry, output_images=output_images, verified=verified)

    notes: list[str] = []
    breakdown: dict[str, float] = {}
    input_usd = 0.0
    output_usd = 0.0

    if usage is None:
        notes.append("API response had no usage_metadata — cost not estimated.")
        return CostEstimate(model=model, usd=0.0, verified=verified, tokens=tokens, notes=notes)

    if unit != "per_million_tokens":
        notes.append(f"Model billed as '{unit}', not supported by this calculator — check your provider's billing directly.")
        return CostEstimate(model=model, usd=0.0, verified=False, tokens=tokens, notes=notes)

    # Prefer per-modality rates when the response reported a modality
    # breakdown and we have rates for it (most accurate — reflects what
    # was actually sent). Otherwise fall back to a flat input rate.
    modality_rates_available = any(
        f"input_{m.lower()}" in entry for m in usage.prompt_modality_breakdown
    )
    if usage.prompt_modality_breakdown and modality_rates_available:
        for modality, mtokens in usage.prompt_modality_breakdown.items():
            key = f"input_{modality.lower()}"
            rate = entry.get(key)
            if rate is None:
                notes.append(f"No rate for modality '{modality}' ({mtokens} tokens not costed).")
                continue
            cost = mtokens / 1_000_000 * rate
            breakdown[key] = breakdown.get(key, 0.0) + cost
            input_usd += cost
    elif "input" in entry:
        input_usd = usage.prompt_tokens / 1_000_000 * entry["input"]
        breakdown["input"] = input_usd
    elif "input_text" in entry:
        input_usd = usage.prompt_tokens / 1_000_000 * entry["input_text"]
        breakdown["input_text"] = input_usd
    else:
        logger.warning("No input rate configured for model '%s'", model)
        notes.append("No input rate found for this model.")

    output_rate_key = None
    if output_images > 0 and "output_image" in entry:
        output_rate_key = "output_image"
        notes.append("Output cost uses the image rate for the full output token count.")
    elif "output_text" in entry:
        output_rate_key = "output_text"
    elif "output_audio" in entry:
        output_rate_key = "output_audio"
    elif "output" in entry:
        output_rate_key = "output"

    if output_rate_key:
        output_rate = entry[output_rate_key]
        output_usd = usage.output_tokens / 1_000_000 * output_rate
        breakdown[output_rate_key] = output_usd

        # Reasoning/"thinking" tokens are a separate bucket in Google's
        # schema but bill at the same output rate -- fold them in rather
        # than silently drop them from the total, which would undercount
        # any call to a thinking-capable model.
        if usage.thoughts_tokens:
            thinking_usd = usage.thoughts_tokens / 1_000_000 * output_rate
            output_usd += thinking_usd
            breakdown["thinking"] = thinking_usd
            notes.append(f"Includes {usage.thoughts_tokens:,} reasoning/thinking tokens at the output rate.")
    else:
        logger.warning("No output rate configured for model '%s'", model)
        notes.append("No output rate found for this model.")

    # Tool-use tokens (results fed back to the model) bill at the input
    # rate. Always 0 today since nothing in this app uses function calling,
    # but captured so a future tool-using call isn't silently undercounted.
    if usage.tool_use_prompt_tokens:
        input_rate = entry.get("input") or entry.get("input_text")
        if input_rate:
            tool_use_usd = usage.tool_use_prompt_tokens / 1_000_000 * input_rate
            input_usd += tool_use_usd
            breakdown["tool_use"] = tool_use_usd
            notes.append(f"Includes {usage.tool_use_prompt_tokens:,} tool-use tokens at the input rate.")

    if not verified:
        notes.append("Rate unverified against an official pricing source — confirm against your provider's actual billing.")

    return CostEstimate(
        model=model,
        usd=input_usd + output_usd,
        verified=verified,
        input_usd=input_usd,
        output_usd=output_usd,
        breakdown=breakdown,
        tokens=tokens,
        notes=notes,
    )


def _estimate_video_cost(
    *,
    model: str,
    entry: dict[str, Any],
    duration_seconds: float,
    resolution: str | None,
    verified: bool,
) -> CostEstimate:
    """Veo bills per second of generated video, not per token."""
    notes: list[str] = []
    if duration_seconds <= 0:
        notes.append("No duration provided — cost not estimated.")
        return CostEstimate(model=model, usd=0.0, verified=verified, notes=notes)

    is_4k = (resolution or "").lower() in {"4k", "2160p"}
    rate = entry.get("rate_4k") if is_4k else entry.get("rate_standard")
    if rate is None:
        notes.append(f"No rate configured for resolution '{resolution}'.")
        return CostEstimate(model=model, usd=0.0, verified=verified, notes=notes)

    output_usd = duration_seconds * rate
    if not verified:
        notes.append("Rate unverified against an official pricing source — confirm against your provider's actual billing.")

    return CostEstimate(
        model=model,
        usd=output_usd,
        verified=verified,
        output_usd=output_usd,
        breakdown={"output_video_seconds": output_usd},
        tokens={"prompt": 0, "output": 0},
        notes=notes,
    )


def _estimate_flat_image_cost(
    *, model: str, entry: dict[str, Any], output_images: int, verified: bool
) -> CostEstimate:
    """Imagen bills a flat rate per image, not per token."""
    notes: list[str] = []
    rate = entry.get("rate_per_image")
    if rate is None:
        notes.append("No per-image rate configured for this model.")
        return CostEstimate(model=model, usd=0.0, verified=verified, notes=notes)
    count = max(output_images, 1)
    output_usd = count * rate
    if not verified:
        notes.append("Rate unverified against an official pricing source — confirm against your provider's actual billing.")
    return CostEstimate(
        model=model,
        usd=output_usd,
        verified=verified,
        output_usd=output_usd,
        breakdown={"output_images": output_usd},
        tokens={"prompt": 0, "output": 0},
        notes=notes,
    )


def summarize_costs(calls: list[dict[str, Any]], pricing_table: dict[str, Any]) -> dict[str, Any]:
    """Roll up cost estimates across every Gemini call a capability made.

    Each call dict: {label, model, usage, output_images (optional)}.
    """
    entries: list[dict[str, Any]] = []
    total = 0.0
    total_input_usd = 0.0
    total_output_usd = 0.0
    any_unverified = False
    total_prompt_tokens = 0
    total_output_tokens = 0
    total_thoughts_tokens = 0

    for call in calls:
        est = estimate_cost(
            model=call["model"],
            usage=call.get("usage"),
            pricing_table=pricing_table,
            output_images=call.get("output_images", 0),
            duration_seconds=call.get("duration_seconds", 0.0),
            resolution=call.get("resolution"),
            label=call.get("label", ""),
        )
        entries.append({"label": call.get("label", call["model"]), **est.as_dict()})
        total += est.usd
        total_input_usd += est.input_usd
        total_output_usd += est.output_usd
        total_prompt_tokens += est.tokens.get("prompt", 0)
        total_output_tokens += est.tokens.get("output", 0)
        total_thoughts_tokens += est.tokens.get("thoughts", 0)
        if not est.verified:
            any_unverified = True

    logger.debug(
        "summarize_costs: %d call(s), total=$%.6f, unverified=%s",
        len(calls), total, any_unverified,
    )

    return {
        "total_usd": round(total, 6),
        "total_input_usd": round(total_input_usd, 6),
        "total_output_usd": round(total_output_usd, 6),
        "any_unverified": any_unverified,
        "total_prompt_tokens": total_prompt_tokens,
        "total_output_tokens": total_output_tokens,
        "total_thoughts_tokens": total_thoughts_tokens,
        "calls": entries,
        "pricing_last_verified": (pricing_table or {}).get("last_verified"),
        "pricing_source_url": (pricing_table or {}).get("source_url"),
    }
