"""Segment 11: Recap — choose, measure, improve (14:15-15:00). ~30s."""
from iav.capabilities.video_hybrid_segment import SegmentPlan
from scripts.full_lesson._shared import infog

PLAN = SegmentPlan(
    title="Seg 11: Recap",
    beats=[
        infog(10,
              "Title at top in large bold dark navy: 'THE FRAMEWORK'. "
              "Centre: a clean numbered checklist with five items, each "
              "with a soft-green checkmark on the left and the label in "
              "navy sans-serif on the right. Top to bottom: '1. Clarify "
              "the goal', '2. Separate essential from desirable', '3. "
              "Weigh evidence', '4. Compare trade-offs', '5. Review the "
              "result'. Generous spacing.",
              "Animate: the title appears first, then each checklist item "
              "appears one by one top to bottom, with the green checkmark "
              "animating in first (small bounce) followed by the labelled "
              "line typing in to the right of it."),
        infog(10,
              "Title: 'CHOOSE, MEASURE, IMPROVE'. Centre: three large navy "
              "circular badges in a row, each with a short label inside in "
              "bold sans-serif: 'CHOOSE' (left, with a target icon), "
              "'MEASURE' (middle, with a gauge icon), 'IMPROVE' (right, "
              "with an upward-arrow icon). A navy arrow connects each "
              "badge to the next, and a dashed arrow curves from IMPROVE "
              "back to CHOOSE closing the loop. Caption underneath in "
              "slate-gray: 'The framework is a loop, not a line.'",
              "Animate: the three badges fade in from left to right in "
              "sequence, with their icons appearing first then the labels. "
              "The forward arrows between them appear as each badge lands. "
              "Last: the dashed curved arrow from IMPROVE back to CHOOSE "
              "draws itself, closing the loop. The caption types in."),
    ],
    narration_script=(
        "Let's pull it together. Clarify the goal. Separate what's essential "
        "from what's merely desirable. Weigh the evidence, not the "
        "impression. Compare the real trade-offs. And review the result, "
        "so the next decision is a better one. "
        "Choose, measure, improve. That's the whole thing. A loop, not a "
        "line. You don't just make decisions -- you learn to make them "
        "better. One at a time."
    ),
)
