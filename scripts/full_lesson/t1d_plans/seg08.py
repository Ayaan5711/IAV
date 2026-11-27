"""Segment 8 — Life crossroads. T1d pattern (mixed realistic + infog)."""
from scripts.full_lesson.t1d_runner import SegmentPlanV2, SubShot


PLAN = SegmentPlanV2(
    title="Seg 8: Life crossroads",
    output_name="t1d_seg08",
    sub_shots=[
        # BEAT 1 -- realistic: fork in park
        SubShot(
            kind="omni_realistic",
            is_beat_start=True,
            narration=(
                "Big life decisions -- a career choice, picking a course of "
                "study, relocating to a new city -- have the same shape as "
                "everyday choices."
            ),
            slide=(
                "Realistic commercial-style video, shallow depth of field, "
                "cinematic quality. A young adult in their early twenties "
                "stands on a quiet path at a fork in a park, looking "
                "thoughtfully at a wooden signpost with two arrow-shaped "
                "boards pointing in different directions. Soft golden "
                "evening light. Wide shot, contemplative mood, slow gentle "
                "motion. The signpost letters are indistinct."
            ),
        ),

        # BEAT 2 -- BIG DECISIONS, SAME SHAPE (branching tree)
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration="A goal. Alternatives. Criteria.",
            slide=(
                "Title at top in bold dark navy sans-serif: 'BIG "
                "DECISIONS, SAME SHAPE'. Centre: a simple branching tree "
                "diagram with a central top node labelled 'A CROSSROADS' "
                "in navy. Three empty slate-gray rounded rectangles are "
                "positioned below where branch labels will go (no "
                "connecting lines yet). Clean 16:9 landscape. Spell exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration="But the dimensions are different.",
            edit_instruction=(
                "Draw three navy lines diverging from the 'A CROSSROADS' "
                "top node, connecting it to the three empty rectangles "
                "below. Also fill in the three leaf labels: left 'CAREER', "
                "centre 'EDUCATION', right 'RELOCATION' in clean navy "
                "sans-serif inside each rectangle. Keep EVERYTHING ELSE "
                "exactly as is -- same title, same top node. Spell exactly."
            ),
            slide="",
        ),

        # BEAT 3 -- THE DIMENSIONS SHIFT (four bar columns)
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration=(
                "We weigh interests. We weigh values. We weigh feasibility."
            ),
            slide=(
                "Title at top in bold dark navy sans-serif: 'THE DIMENSIONS "
                "SHIFT'. Centre: four columns arranged across the slide, "
                "each column labelled at the top in bold navy: "
                "'INTERESTS', 'VALUES', 'FEASIBILITY', 'GROWTH'. Each "
                "column has an empty slate-gray vertical bar outline below "
                "it (no filled bar values yet). Clean 16:9 landscape. "
                "Spell exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "We weigh how much the choice sets up the next few years of growth."
            ),
            edit_instruction=(
                "Fill in all four column bars with soft-green fills at "
                "different heights to show relative importance (e.g., "
                "INTERESTS tall, VALUES medium, FEASIBILITY medium-tall, "
                "GROWTH tall). Add a slate-gray caption below: 'Different "
                "from a purchase -- these matter more.' Keep EVERYTHING "
                "ELSE exactly as is -- same title, same four column labels. "
                "Spell exactly."
            ),
            slide="",
        ),

        # BEAT 4 -- UNCERTAINTY AND REVERSIBILITY (two circular)
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration=(
                "And one dimension you don't usually think about when "
                "buying cookies: how hard is this to reverse?"
            ),
            slide=(
                "Title at top in bold dark navy sans-serif: 'UNCERTAINTY "
                "AND REVERSIBILITY'. Centre: two circular diagrams side by "
                "side. Left circle has a LOCK icon inside, labelled "
                "underneath 'HARD TO REVERSE' in bold navy. Right circle "
                "has a CIRCULAR ARROW icon inside, labelled underneath "
                "'EASY TO ADJUST' in bold navy. No caption below yet. "
                "Clean 16:9 landscape. Spell exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "A rental is easy to undo. A house purchase is harder. "
                "Marriage, harder still."
            ),
            edit_instruction=(
                "Keep the slide exactly the same -- do not change anything. "
                "Same title, same two circular diagrams with their icons "
                "and labels. No new text."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "Factor in reversibility: the less reversible, the more "
                "care the decision deserves upfront."
            ),
            edit_instruction=(
                "Add a slate-gray caption below the two circular diagrams: "
                "'Weigh how much a wrong move will cost to undo.' Keep "
                "EVERYTHING ELSE exactly as is -- same title, same two "
                "diagrams with their icons and labels. Spell exactly."
            ),
            slide="",
        ),
    ],
)
