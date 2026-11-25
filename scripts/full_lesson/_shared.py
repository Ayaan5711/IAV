"""Shared helpers for Selection Criterion segment scripts.

Every segment file imports these so the per-segment file only has to
contain the content-specific prompts, not boilerplate. Also enforces
a single visual style across all 11 segments (consistent navy/green
palette, consistent typography) by concatenating STYLE_BASE into every
infographic prompt.
"""
from iav.capabilities.video_hybrid_segment import Beat

STYLE_BASE = (
    "Clean professional educational infographic slide, flat 2D design style, white "
    "background, 16:9 widescreen landscape aspect ratio. Dark navy sans-serif "
    "typography (bold navy for titles, regular navy for labels, slate-gray for "
    "supporting captions). Soft green for correct/preferred/successful items, "
    "soft gray for rejected/weaker items, white space generously used. Polished "
    "corporate L&D training graphic style, consistent with a cognitive-skills "
    "lesson series. No photographic elements, no watermarks, no logos, no stray "
    "text outside the labels specified."
)

ANIMATE_PRESERVE = (
    "Preserve the exact flat 2D motion graphics style and every existing element "
    "in this infographic -- same white background, same navy titles, same color "
    "palette, same sans-serif text labels. Do not re-draw or re-style. Keep all "
    "text labels exactly as currently written. Do not add any new text. "
)

VEO_REAL_BASE = (
    "Realistic commercial-style video, shallow depth of field, cinematic quality. "
    "No readable text on signage, products, or packaging. No captions or titles "
    "appearing on screen."
)


def veo(duration: int, prompt: str, *, chain: bool = False) -> Beat:
    """Realistic Veo beat. duration must be 4, 6, or 8."""
    return Beat(
        kind="veo",
        duration_seconds=duration,
        prompt=f"{VEO_REAL_BASE} {prompt}",
        chain_from_previous=chain,
    )


def infog(duration: int, slide: str, animate: str) -> Beat:
    """Infographic beat that uses Nano Banana + Omni edit for motion
    graphics. duration clamped to 10 (Omni edit's hard input cap)."""
    return Beat(
        kind="infographic_animated",
        duration_seconds=min(duration, 10),
        prompt=f"{STYLE_BASE} {slide}::ANIMATE::{ANIMATE_PRESERVE} {animate}",
    )
