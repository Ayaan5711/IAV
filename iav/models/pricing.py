"""Cost estimation from Gemini API token usage.

Token counts come straight from usage_metadata on each response — real,
not estimated. Dollar costs are computed from those counts against the
rates in config.yaml's pricing table, which mixes confirmed and
unconfirmed rates (see the `verified` flag per model). Cloud Billing is
the source of truth for actual charges, not this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UsageInfo:
    prompt_tokens: int = 0
    output_tokens: int = 0
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
    label: str = "",
) -> CostEstimate:
    models = (pricing_table or {}).get("models", {})
    entry = models.get(model)
    tokens = {
        "prompt": usage.prompt_tokens if usage else 0,
        "output": usage.output_tokens if usage else 0,
    }

    if entry is None:
        return CostEstimate(
            model=model,
            usd=0.0,
            verified=False,
            tokens=tokens,
            notes=[f"No pricing entry for '{model}' in config.yaml -> pricing.models."],
        )

    verified = bool(entry.get("verified", False))
    notes: list[str] = []
    breakdown: dict[str, float] = {}
    input_usd = 0.0
    output_usd = 0.0

    if usage is None:
        notes.append("API response had no usage_metadata — cost not estimated.")
        return CostEstimate(model=model, usd=0.0, verified=verified, tokens=tokens, notes=notes)

    unit = entry.get("unit", "per_million_tokens")
    if unit != "per_million_tokens":
        notes.append(f"Model billed as '{unit}', not supported by this calculator — check Cloud Billing.")
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
        notes.append("No input rate found for this model.")

    if output_images > 0 and "output_image" in entry:
        output_usd = usage.output_tokens / 1_000_000 * entry["output_image"]
        breakdown["output_image"] = output_usd
        notes.append("Output cost uses the image rate for the full output token count.")
    elif "output_text" in entry:
        output_usd = usage.output_tokens / 1_000_000 * entry["output_text"]
        breakdown["output_text"] = output_usd
    elif "output_audio" in entry:
        output_usd = usage.output_tokens / 1_000_000 * entry["output_audio"]
        breakdown["output_audio"] = output_usd
    elif "output" in entry:
        output_usd = usage.output_tokens / 1_000_000 * entry["output"]
        breakdown["output"] = output_usd
    else:
        notes.append("No output rate found for this model.")

    if not verified:
        notes.append("Rate unverified against an official Google source — confirm in Cloud Billing.")

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

    for call in calls:
        est = estimate_cost(
            model=call["model"],
            usage=call.get("usage"),
            pricing_table=pricing_table,
            output_images=call.get("output_images", 0),
            label=call.get("label", ""),
        )
        entries.append({"label": call.get("label", call["model"]), **est.as_dict()})
        total += est.usd
        total_input_usd += est.input_usd
        total_output_usd += est.output_usd
        total_prompt_tokens += est.tokens.get("prompt", 0)
        total_output_tokens += est.tokens.get("output", 0)
        if not est.verified:
            any_unverified = True

    return {
        "total_usd": round(total, 6),
        "total_input_usd": round(total_input_usd, 6),
        "total_output_usd": round(total_output_usd, 6),
        "any_unverified": any_unverified,
        "total_prompt_tokens": total_prompt_tokens,
        "total_output_tokens": total_output_tokens,
        "calls": entries,
        "pricing_last_verified": (pricing_table or {}).get("last_verified"),
        "pricing_source_url": (pricing_table or {}).get("source_url"),
    }
