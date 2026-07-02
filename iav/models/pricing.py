"""Cost estimation from real Gemini API token usage.

Two different kinds of numbers flow through this module, and they must
never be conflated:

  1. Token counts — REAL. Pulled directly from each API response's
     ``usage_metadata``. Google's servers report exactly what was billed
     for that call. Never estimated, never rounded for effect.

  2. Dollar costs — ESTIMATES. Computed by multiplying real token counts
     by list-price rates kept in config.yaml's ``pricing`` section. Some
     of those rates come from Google's official Vertex AI pricing page
     (marked ``verified: true``); others could not be confirmed against
     an official source at the time they were added (marked
     ``verified: false``). Actual GCP invoices can differ from list price
     due to committed-use discounts, promotional credits, or price
     changes since this table was last checked — Cloud Billing is the
     source of truth, not this module.

Every cost estimate this module produces carries its own ``verified``
flag and human-readable notes, so the UI can show — per call, not just
in aggregate — which numbers are solid and which are a best guess.
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
    breakdown: dict[str, float] = field(default_factory=dict)
    tokens: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "usd": round(self.usd, 6),
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
    """Estimate the cost of a single Gemini call.

    Always returns a result, even when pricing can't be determined —
    in that case ``usd`` is 0.0 and ``notes`` explains why, rather than
    silently reporting an incorrect number.
    """
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
            notes=[f"No pricing entry for '{model}' in config.yaml -> pricing.models. Cost not estimated."],
        )

    verified = bool(entry.get("verified", False))
    notes: list[str] = []
    breakdown: dict[str, float] = {}
    total = 0.0

    if usage is None:
        notes.append("No usage metadata returned by the API for this call.")
        return CostEstimate(model=model, usd=0.0, verified=verified, tokens=tokens, notes=notes)

    unit = entry.get("unit", "per_million_tokens")
    if unit != "per_million_tokens":
        notes.append(
            f"Model '{model}' is billed as '{unit}', which this calculator "
            "doesn't support yet. Cost not estimated — check Cloud Billing."
        )
        return CostEstimate(model=model, usd=0.0, verified=False, tokens=tokens, notes=notes)

    # --- Input side -----------------------------------------------------
    # Prefer a per-modality breakdown (most accurate — reflects exactly
    # what was sent: text vs image vs audio vs video) when both the usage
    # data and matching rates are available. Otherwise fall back to a
    # flat input rate applied to the total prompt tokens.
    modality_rates_available = any(
        f"input_{m.lower()}" in entry for m in usage.prompt_modality_breakdown
    )
    if usage.prompt_modality_breakdown and modality_rates_available:
        for modality, mtokens in usage.prompt_modality_breakdown.items():
            key = f"input_{modality.lower()}"
            rate = entry.get(key)
            if rate is None:
                notes.append(
                    f"No input rate configured for modality '{modality}' "
                    f"({mtokens} tokens not included in the estimate)."
                )
                continue
            cost = mtokens / 1_000_000 * rate
            breakdown[key] = breakdown.get(key, 0.0) + cost
            total += cost
    elif "input" in entry:
        cost = usage.prompt_tokens / 1_000_000 * entry["input"]
        breakdown["input"] = cost
        total += cost
    elif "input_text" in entry:
        cost = usage.prompt_tokens / 1_000_000 * entry["input_text"]
        breakdown["input_text"] = cost
        total += cost
    else:
        notes.append("No input pricing rate found for this model; input cost not estimated.")

    # --- Output side ------------------------------------------------------
    if output_images > 0 and "output_image" in entry:
        cost = usage.output_tokens / 1_000_000 * entry["output_image"]
        breakdown["output_image"] = cost
        total += cost
        notes.append(
            "Output cost uses the image-output rate applied to the full "
            "output token count (any accompanying text tokens are approximated "
            "at the same rate)."
        )
    elif "output_text" in entry:
        cost = usage.output_tokens / 1_000_000 * entry["output_text"]
        breakdown["output_text"] = cost
        total += cost
    elif "output_audio" in entry:
        cost = usage.output_tokens / 1_000_000 * entry["output_audio"]
        breakdown["output_audio"] = cost
        total += cost
    elif "output" in entry:
        cost = usage.output_tokens / 1_000_000 * entry["output"]
        breakdown["output"] = cost
        total += cost
    else:
        notes.append("No output pricing rate found for this model; output cost not estimated.")

    if not verified:
        notes.append(
            "Pricing for this model is UNVERIFIED against an official Google "
            "source — treat this number as directional, not authoritative. "
            "Confirm in the Cloud Billing console before relying on it."
        )

    return CostEstimate(model=model, usd=total, verified=verified, breakdown=breakdown, tokens=tokens, notes=notes)


def summarize_costs(
    calls: list[dict[str, Any]],
    pricing_table: dict[str, Any],
) -> dict[str, Any]:
    """Roll up cost estimates across every Gemini call a capability made.

    ``calls`` is a list of dicts, one per call, each with:
        label: str            -- human-readable step name (e.g. "transcribe")
        model: str             -- model ID used for that call
        usage: UsageInfo|None  -- usage metadata from that call's response
        output_images: int     -- optional, defaults to 0

    Returns a dict with a grand total, a per-call breakdown, and an
    ``any_unverified`` flag so the UI can show a single warning banner
    rather than requiring the caller to inspect every entry.
    """
    entries: list[dict[str, Any]] = []
    total = 0.0
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
        total_prompt_tokens += est.tokens.get("prompt", 0)
        total_output_tokens += est.tokens.get("output", 0)
        if not est.verified:
            any_unverified = True

    return {
        "total_usd": round(total, 6),
        "any_unverified": any_unverified,
        "total_prompt_tokens": total_prompt_tokens,
        "total_output_tokens": total_output_tokens,
        "calls": entries,
        "pricing_last_verified": (pricing_table or {}).get("last_verified"),
        "pricing_source_url": (pricing_table or {}).get("source_url"),
    }
