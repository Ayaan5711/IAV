"""Hybrid pipeline demo: one 72-second segment of the Selection Criterion
15-minute concept video, built end-to-end on this app's existing
capabilities.

Covers "Essential and desirable criteria" (the 3:30-5:15 segment of the
TCS iON outline), trimmed to 72 seconds, with three production techniques
in one video:

    Beat 1 (Veo, 8s)             Realistic: shopper comparing two laptops
                                 in a store aisle.
    Beat 2 (Nano Banana, 16s)    Infographic: "Essential Requirements"
                                 filter graphic.
    Beat 3 (Nano Banana, 16s)    Infographic: "Desirable Preferences"
                                 cards graphic.
    Beat 4 (Veo, 8s)             Realistic: the shopper makes the final
                                 decision, continuing visually from beat 1.
    (continued below: 24s of narration pacing over beats 2+3's longer
    durations means total = 48s video; adjusted below to 72s --
    see beat list.)

Narration: one Gemini TTS track across the whole segment, muxed over the
assembled silent video.

Run:
    python scripts/hybrid_selection_criterion_demo.py

Expected cost: ~$1.60-2.50 (Veo lite tier + Nano Banana text/image
tokens + TTS). Expected wall-clock: ~4-5 minutes (sequential, bounded by
Veo's ~45-55s per call).
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("hybrid-demo")

# Load .env for GOOGLE_APPLICATION_CREDENTIALS before importing anything
# that touches the Vertex AI client.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from iav.capabilities.base import CapabilityInput
from iav.capabilities.video_hybrid_segment import (
    Beat,
    SegmentPlan,
    VideoHybridSegment,
)


# --------------------------------------------------------------------
# The plan: 4 beats totalling 72 seconds. Prompts and script written to
# match the Selection Criterion outline's 3:30-5:15 segment.
# --------------------------------------------------------------------

PLAN = SegmentPlan(
    title="Essential and desirable criteria (Selection Criterion, 3:30-5:15, 72s demo)",
    beats=[
        # Beat 1: realistic opening (16s = 8+8 chained for better continuity)
        Beat(
            kind="veo",
            duration_seconds=8,
            prompt=(
                "A realistic commercial-style video, shallow depth of field, warm indoor "
                "store lighting. A man in his thirties stands in a bright electronics-store "
                "aisle in front of a shelf of laptops. He picks up two different laptops, "
                "one in each hand, and looks at them thoughtfully, comparing them. His "
                "shopping cart is visible behind him. No readable text, no signage, no "
                "on-screen captions."
            ),
        ),
        Beat(
            kind="veo",
            duration_seconds=8,
            chain_from_previous=True,
            prompt=(
                "The same man continues to compare the two laptops, turning each one to "
                "look at its features. He purses his lips thoughtfully. Same store, same "
                "lighting, same wardrobe. No readable text, no signage."
            ),
        ),
        # Beat 2: infographic (20s) -- essential-requirements filter
        Beat(
            kind="infographic",
            duration_seconds=20,
            prompt=(
                "Create a clean, professional educational infographic slide, flat design "
                "style, on a white background, 16:9 widescreen landscape aspect ratio. "
                "The slide is titled at the top in bold dark navy sans-serif text: "
                '"ESSENTIAL REQUIREMENTS". Below the title, show a simple illustrated '
                "funnel-shaped filter in the centre of the slide. On the LEFT side of the "
                "funnel, show four small rounded rectangular icons representing options, "
                "labelled in clean sans-serif: 'Laptop A', 'Laptop B', 'Laptop C', "
                "'Laptop D'. Arrows show them entering the funnel. On the RIGHT side of "
                "the funnel, only two of those rectangles emerge: 'Laptop B' and "
                "'Laptop D'. Under the funnel, in smaller slate-gray text, write three "
                "example essential criteria: 'Within budget', 'Fits the use case', "
                "'Available in stock'. The whole slide should look like a polished "
                "corporate L&D training graphic. Use a limited palette: dark navy for "
                "text, soft green for 'passed' items, soft gray for 'rejected' items. No "
                "watermarks, no logos, no stray text, no photographic elements."
            ),
        ),
        # Beat 3: infographic (20s) -- desirable preferences cards
        Beat(
            kind="infographic",
            duration_seconds=20,
            prompt=(
                "Create a clean, professional educational infographic slide, flat design "
                "style, on a white background, 16:9 widescreen landscape aspect ratio, "
                "visually consistent with a corporate L&D training series. The slide is "
                "titled at the top in bold dark navy sans-serif text: 'DESIRABLE "
                "PREFERENCES'. Below the title, show two rounded rectangular 'option "
                "cards' side by side in the centre, labelled 'Laptop B' and 'Laptop D' in "
                "sans-serif. Each card has three small horizontal rating bars underneath "
                "showing preference scores, labelled 'Weight', 'Battery life', and "
                "'Screen quality'. Laptop B's bars are mostly short/medium; Laptop D's "
                "bars are mostly longer, indicating a stronger match. Below the cards, "
                "in smaller slate-gray text, write: 'Preferences break ties between "
                "acceptable options.' Use the same palette as the previous slide: dark "
                "navy for text, soft green for strong scores, light gray for weaker "
                "scores. No watermarks, no logos, no photographic elements, no stray text."
            ),
        ),
        # Beat 4: realistic close (8s), not chained -- fresh scene of the
        # decision moment. Chaining from beat-1-last-frame would require
        # the capability to carry a frame across the infographic beats
        # (future enhancement); for this demo, a fresh scene reads
        # cleanly as a narrative cut back to the shopper.
        Beat(
            kind="veo",
            duration_seconds=8,
            prompt=(
                "A realistic commercial-style video in the same bright electronics-store "
                "aisle, shallow depth of field, warm lighting. The same man in his "
                "thirties as before, in the same wardrobe, now smiles, decisively places "
                "one laptop into his shopping cart, and begins to push the cart forward "
                "down the aisle. Satisfied expression. No readable text, no signage."
            ),
        ),
    ],
    narration_script=(
        "When we're comparing options, not every requirement matters the same way. "
        "Some requirements are essential. An option that doesn't meet them is out, no "
        "matter how good the rest of it looks. Others are only desirable. They don't "
        "disqualify an option; they just help us choose between the ones that are "
        "still in the running. "
        "Let's see how that plays out in practice. "
        "Suppose we're choosing a laptop. First, we apply the essential requirements. "
        "It has to be within budget. It has to fit the use case. And it has to actually "
        "be available to buy. Any option that fails one of these is out. "
        "Now, from the laptops still in the running, we look at the desirable "
        "preferences. How light is it? How long does the battery last? How good is the "
        "screen? These are the preferences that break ties between options we'd be "
        "happy with. "
        "The decision becomes much clearer this way: we rule out before we rank."
    ),
)


def main() -> int:
    t0 = time.perf_counter()
    cap = VideoHybridSegment()
    result = cap.process(CapabilityInput(params={"plan": PLAN}))
    elapsed = time.perf_counter() - t0

    print()
    print("=" * 72)
    print("DONE")
    print("=" * 72)
    print(f"Final video:       {result.file_path}")
    print(f"Beats:             {result.metadata['beat_count']} "
          f"({'/'.join(result.metadata['beat_kinds'])})")
    print(f"Bytes:             {result.metadata['output_bytes']:,}")
    print(f"Elapsed:           {elapsed:.0f}s")
    print(f"Est. cost USD:     ${result.metadata['cost']['total_usd']:.4f}")
    print(f"Narration (first 160 chars):")
    print(f"  {(result.text or '')[:160]}...")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
