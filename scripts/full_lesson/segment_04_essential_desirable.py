"""Segment 4 of the Selection Criterion 15-min lesson.
3:30-5:15 — 'Essential and desirable criteria'. 105 seconds.

Uses infographic_animated for the two infographic beats (Nano Banana +
Omni edit = real element animation). Realistic beats bracket the
infographics to pace the segment and give the learner something to
anchor the abstract concepts to.

Beat plan (total ~105s video):
  1. Realistic Veo (8s) — shopper comparing two laptops
  2. Realistic Veo (8s, chained) — shopper studying the features
  3. Animated infographic (10s) — Essential Requirements funnel (what we proved)
  4. Animated infographic (10s, 2nd Omni call) — same funnel, late-stage animation
  5. Animated infographic (10s) — Desirable Preferences cards appearing
  6. Animated infographic (10s, 2nd call) — preference bars filling in
  7. Realistic Veo (8s) — shopper making the final decision
  = ~64s video. Pad narration to not require more than that;
     for a 105s target, extend with more beats or ken-burns pauses.

To keep this validation beat count tractable and within budget we aim for
~55-65s of generated content for segment 4 specifically; the full
15-minute lesson balances across all 11 segments.
"""

from iav.capabilities.video_hybrid_segment import Beat, SegmentPlan


# ==================================================================
# Infographic slide 1: the funnel
# ==================================================================
_FUNNEL_SLIDE_PROMPT = (
    "Create a clean, professional educational infographic slide, flat design "
    "style, on a white background, 16:9 widescreen landscape aspect ratio. "
    "The slide is titled at the top in bold dark navy sans-serif text: "
    "'ESSENTIAL REQUIREMENTS'. Below the title, show a simple illustrated "
    "funnel-shaped filter in the centre of the slide. On the LEFT side of the "
    "funnel, show four small rounded rectangular icons representing options, "
    "labelled in clean sans-serif: 'Laptop A', 'Laptop B', 'Laptop C', "
    "'Laptop D'. Arrows show them entering the funnel. On the RIGHT side of "
    "the funnel, only two of those rectangles emerge: 'Laptop B' and "
    "'Laptop D' in soft green. Under the funnel, in smaller slate-gray text, "
    "write three example essential criteria: 'Within budget', 'Fits the use "
    "case', 'Available in stock'. Polished corporate L&D training graphic. "
    "Use a limited palette: dark navy for text, soft green for 'passed' "
    "items, soft gray for 'rejected' items. No watermarks, no logos, no "
    "stray text, no photographic elements."
)

_FUNNEL_ANIMATE_PROMPT = (
    "Preserve the exact flat 2D motion graphics style and every existing "
    "element in this infographic -- same white background, same navy "
    "titles, same funnel shape, same color palette, same sans-serif text "
    "labels. Do not re-draw or re-style. ONLY add element-level "
    "animation: the four Laptop option rectangles on the left should "
    "slide to the right one by one into the funnel in sequence. Then show "
    "only two rectangles (Laptop B and Laptop D) emerging on the right in "
    "soft green. Keep all text labels exactly as currently written. Do "
    "not add any new text."
)


# ==================================================================
# Infographic slide 2: preference cards
# ==================================================================
_CARDS_SLIDE_PROMPT = (
    "Create a clean, professional educational infographic slide, flat "
    "design style, on a white background, 16:9 widescreen landscape "
    "aspect ratio. Visually consistent with a corporate L&D training "
    "series: same dark navy sans-serif typography, soft green accent, "
    "soft gray for secondary. Title at the top in bold dark navy "
    "sans-serif text: 'DESIRABLE PREFERENCES'. Below the title, show "
    "two rounded rectangular 'option cards' side by side in the centre, "
    "labelled 'Laptop B' and 'Laptop D' in sans-serif. Each card has "
    "three small horizontal rating bars underneath, labelled from top to "
    "bottom: 'Weight', 'Battery life', 'Screen quality'. Laptop B's bars "
    "are mostly short/medium in soft gray; Laptop D's bars are mostly "
    "longer in soft green, indicating a stronger match. Below both cards, "
    "in smaller slate-gray text: 'Preferences break ties between "
    "acceptable options.' Clean minimalist design, no watermarks, no "
    "logos, no stray text, no photographic elements."
)

_CARDS_ANIMATE_PROMPT = (
    "Preserve the exact flat 2D motion graphics style and every existing "
    "element in this infographic -- same white background, same navy "
    "title 'DESIRABLE PREFERENCES', same two 'Laptop B' and 'Laptop D' "
    "cards, same preference bars with labels 'Weight', 'Battery life', "
    "'Screen quality', same color palette. Do not re-draw or re-style. "
    "ONLY animate: the two option cards fade in from the left and right "
    "sides and settle into their centre positions, then each preference "
    "bar fills in horizontally from left to right (gray for Laptop B's "
    "shorter bars, green for Laptop D's longer bars). Keep all text "
    "labels exactly as currently written. Do not add any new text."
)


PLAN = SegmentPlan(
    title="Segment 4: Essential and desirable criteria (3:30-5:15, 56s demo)",
    beats=[
        # Opening realistic beat: 8s shopper comparing laptops
        Beat(
            kind="veo",
            duration_seconds=8,
            prompt=(
                "Realistic commercial-style video, shallow depth of field, warm indoor "
                "store lighting. A man in his thirties stands in a bright electronics "
                "store aisle in front of a shelf of laptops. He picks up two laptops, "
                "one in each hand, and looks between them thoughtfully. Shopping cart "
                "visible behind him. No readable text, no signage, no captions."
            ),
        ),
        # Infographic beat 1: Essential Requirements funnel animation (10s)
        Beat(
            kind="infographic_animated",
            duration_seconds=10,
            prompt=f"{_FUNNEL_SLIDE_PROMPT}::ANIMATE::{_FUNNEL_ANIMATE_PROMPT}",
        ),
        # Infographic beat 2: Desirable Preferences cards (10s)
        Beat(
            kind="infographic_animated",
            duration_seconds=10,
            prompt=f"{_CARDS_SLIDE_PROMPT}::ANIMATE::{_CARDS_ANIMATE_PROMPT}",
        ),
        # Closing realistic beat: 8s decisive pickup
        Beat(
            kind="veo",
            duration_seconds=8,
            prompt=(
                "Realistic commercial-style video in a bright electronics-store aisle, "
                "shallow depth of field, warm lighting. A man in his thirties, blue "
                "shirt, decisively places a laptop into his shopping cart and begins "
                "pushing it down the aisle with a satisfied expression. No readable "
                "text, no signage."
            ),
        ),
    ],
    narration_script=(
        "When we're comparing options, not every requirement matters the same way. "
        "Some requirements are essential -- an option that doesn't meet them is "
        "out, no matter how good the rest of it looks. Others are only desirable: "
        "they don't disqualify an option; they help us choose between the ones "
        "still in the running. "
        "Suppose we're choosing a laptop. First, we apply the essential "
        "requirements. It has to be within budget. It has to fit the use case. "
        "It has to actually be available. Anything that fails is out. "
        "Now, from the laptops still in the running, we look at the desirable "
        "preferences -- weight, battery life, screen quality. These are what break "
        "the tie between options we'd be happy with. "
        "The decision becomes clearer this way: we rule out before we rank."
    ),
)
