"""Segment 1 — Selection in everyday life. T1d pattern.

Two omni_realistic beats (grocery woman, dealership man) bracket the
"EVERY DAY, WE CHOOSE" infographic cards reveal. Narration per
sentence.
"""
from scripts.full_lesson.t1d_runner import SegmentPlanV2, SubShot


PLAN = SegmentPlanV2(
    title="Seg 1: Selection in everyday life",
    output_name="t1d_seg01",
    sub_shots=[
        # BEAT 1 -- realistic: grocery, two cookies, compare + cart
        SubShot(
            kind="omni_realistic",
            is_beat_start=True,
            narration=(
                "Every day, we make choices. Which box of cookies to buy."
            ),
            slide=(
                "Realistic commercial-style video, shallow depth of field, cinematic "
                "quality. A woman in her thirties stands in a grocery store aisle "
                "holding two different boxes of cookies, one in each hand, comparing "
                "them thoughtfully, then smiling and placing one box into her "
                "shopping cart before pushing the cart down the aisle. Bright warm "
                "indoor lighting, single continuous take. No readable text."
            ),
        ),

        # BEAT 2 -- realistic: dealership man
        SubShot(
            kind="omni_realistic",
            is_beat_start=True,
            narration="Which car fits the family. Which direction to take in life.",
            slide=(
                "Realistic commercial-style video, shallow depth of field, cinematic "
                "quality. A man in his thirties at a modern car dealership looking "
                "thoughtfully between two different cars (one silver sedan, one blue "
                "compact SUV) parked side by side. Soft natural lighting through "
                "large windows, slow contemplative motion. No readable text."
            ),
        ),

        # BEAT 3 -- infographic: EVERY DAY, WE CHOOSE three cards
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration="These look like very different decisions.",
            slide=(
                "Title at top center in bold dark navy sans-serif: 'EVERY DAY, WE "
                "CHOOSE'. Below the title, three equally-sized rounded rectangular "
                "cards in a row across the centre, each with an empty slate-gray "
                "outline (no illustrations or captions yet). Clean 16:9 landscape. "
                "Generous spacing. Spell every word exactly, no typos."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration="But they share the same shape: we have options,",
            edit_instruction=(
                "Fill in the LEFT card: add a flat navy illustration of a shopping "
                "basket with cookies inside, and a slate-gray caption underneath the "
                "card reading 'What to buy'. Keep EVERYTHING ELSE exactly as is -- "
                "same title, same two empty cards to the right. Spell 'What to buy' "
                "exactly."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration="and we have reasons to prefer one over the others.",
            edit_instruction=(
                "Fill in the CENTRE card: add a flat navy illustration of a car "
                "silhouette, and a slate-gray caption underneath the card reading "
                "'What to drive'. Keep EVERYTHING ELSE exactly as is -- same title, "
                "same left card (basket with 'What to buy'), same right empty card. "
                "Spell 'What to drive' exactly."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "That is what selection is -- not just picking, but picking for a reason."
            ),
            edit_instruction=(
                "Fill in the RIGHT card: add a flat navy illustration of a signpost "
                "at a fork in a path, and a slate-gray caption underneath the card "
                "reading 'Which way to go'. Keep EVERYTHING ELSE exactly as is -- "
                "same title, same two left cards. Spell 'Which way to go' exactly."
            ),
            slide="",
        ),
    ],
)
