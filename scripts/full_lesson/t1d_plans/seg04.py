"""Segment 4 — Essential and desirable criteria. T1d pattern.

Mixed: realistic Omni beats open and close, with two infographic
sub-shot groups (funnel + preference cards) in between.
"""
from scripts.full_lesson.t1d_runner import SegmentPlanV2, SubShot


PLAN = SegmentPlanV2(
    title="Seg 4: Essential and desirable criteria",
    output_name="t1d_seg04",
    sub_shots=[
        # BEAT 1 -- realistic: shopper comparing laptops
        SubShot(
            kind="omni_realistic",
            is_beat_start=True,
            narration=(
                "When we're comparing options, not every requirement matters "
                "the same way."
            ),
            slide=(
                "Realistic commercial-style video, shallow depth of field, warm "
                "indoor store lighting. A man in his thirties stands in a bright "
                "electronics store aisle in front of a shelf of laptops. He "
                "picks up two laptops, one in each hand, and looks between them "
                "thoughtfully. Shopping cart visible behind him. No readable "
                "text, no signage."
            ),
        ),

        # BEAT 2 -- infographic: ESSENTIAL REQUIREMENTS funnel
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration=(
                "Some requirements are essential -- an option that doesn't "
                "meet them is out, no matter how good the rest of it looks."
            ),
            slide=(
                "Title at top in bold dark navy sans-serif: 'ESSENTIAL "
                "REQUIREMENTS'. Centre: a simple illustrated navy funnel "
                "shape (wider at left, narrowing to the right). Entering "
                "the funnel from the left: four small slate-gray rounded "
                "rectangles labelled 'Laptop A', 'Laptop B', 'Laptop C', "
                "'Laptop D'. The right side of the funnel is empty for now. "
                "Clean 16:9 landscape. Spell every word exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "Suppose we're choosing a laptop. First, we apply the "
                "essential requirements."
            ),
            edit_instruction=(
                "Add a slate-gray caption BELOW the funnel listing three "
                "example essential criteria: 'Within budget', 'Fits the use "
                "case', 'Available in stock'. Keep EVERYTHING ELSE exactly "
                "as is -- same title, same funnel, same four laptop "
                "rectangles entering the funnel on the left. Spell exactly."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "It has to be within budget. It has to fit the use case. "
                "It has to actually be available. Anything that fails is out."
            ),
            edit_instruction=(
                "On the RIGHT side of the funnel, make only TWO rectangles "
                "emerge in soft green: 'Laptop B' and 'Laptop D'. The other "
                "two (Laptop A and Laptop C) are NOT shown on the right "
                "side -- they've been filtered out. Keep EVERYTHING ELSE "
                "exactly as is -- same title, same funnel, same four left "
                "rectangles entering, same caption below. Spell exactly."
            ),
            slide="",
        ),

        # BEAT 3 -- infographic: DESIRABLE PREFERENCES cards
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration=(
                "Others are only desirable: they don't disqualify an option; "
                "they help us choose between the ones still in the running."
            ),
            slide=(
                "Title at top in bold dark navy sans-serif: 'DESIRABLE "
                "PREFERENCES'. Centre: two rounded rectangular 'option "
                "cards' side by side, labelled 'Laptop B' and 'Laptop D' in "
                "clean sans-serif. Each card has three empty horizontal "
                "rating bar placeholders underneath, with row labels (top "
                "to bottom): 'Weight', 'Battery life', 'Screen quality'. "
                "All bars are empty slate-gray outlines, no filled values. "
                "Clean 16:9 landscape. Spell every word exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "Now, from the laptops still in the running, we look at the "
                "desirable preferences -- weight, battery life, screen quality."
            ),
            edit_instruction=(
                "Fill in Laptop B's three bars with soft-gray fills, "
                "indicating short-to-medium lengths (Laptop B is weaker on "
                "these preferences). Leave Laptop D's bars still empty. "
                "Keep EVERYTHING ELSE exactly as is -- same title, same two "
                "cards, same labels. Spell exactly."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "These are what break the tie between options we'd be happy with."
            ),
            edit_instruction=(
                "Fill in Laptop D's three bars with soft-green fills, "
                "indicating LONG lengths (Laptop D is stronger on these "
                "preferences). Also add a slate-gray caption below both "
                "cards: 'Preferences break ties between acceptable "
                "options.' Keep EVERYTHING ELSE exactly as is -- same "
                "title, same Laptop B bars. Spell exactly."
            ),
            slide="",
        ),

        # BEAT 4 -- realistic: shopper decides
        SubShot(
            kind="omni_realistic",
            is_beat_start=True,
            narration="The decision becomes clearer this way: we rule out before we rank.",
            slide=(
                "Realistic commercial-style video in a bright electronics-store "
                "aisle, shallow depth of field, warm lighting. A man in his "
                "thirties, blue shirt, decisively places a laptop into his "
                "shopping cart and begins pushing it down the aisle with a "
                "satisfied expression. No readable text, no signage."
            ),
        ),
    ],
)
