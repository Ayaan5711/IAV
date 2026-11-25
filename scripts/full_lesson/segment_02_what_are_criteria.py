"""Segment 2: What are selection criteria? (1:00-2:15). ~40s."""
from iav.capabilities.video_hybrid_segment import SegmentPlan
from scripts.full_lesson._shared import infog

PLAN = SegmentPlan(
    title="Seg 2: Goal, option, criterion",
    beats=[
        infog(10,
              "Title at top in bold dark navy: 'GOAL, OPTION, CRITERION'. Below, "
              "three rounded rectangular cards side-by-side, labelled in large "
              "clean sans-serif: 'GOAL' (left card, with a small star icon), "
              "'OPTION' (centre card, with a small circle icon), 'CRITERION' "
              "(right card, with a small checkmark icon).",
              "Animate: the three labelled cards appear one after another, GOAL "
              "first, then OPTION, then CRITERION. Each card slides into "
              "position from below with a gentle ease. Final state: all three "
              "cards visible, evenly spaced across the middle of the slide."),
        infog(10,
              "Title at top: 'THE GOAL SHAPES THE CRITERIA'. In the centre, a "
              "navy star icon labelled 'GOAL: a warm weekend trip' at the top. "
              "A navy arrow points down from the star to three smaller rounded "
              "rectangular labels in a row below: 'warm clothes', 'lightweight "
              "bag', 'good shoes'. All labels in clean sans-serif, navy on white.",
              "Animate: the GOAL star appears first at top, holds for a moment, "
              "then an arrow draws downward, and the three criterion labels "
              "appear from left to right in sequence under the arrow. "),
        infog(10,
              "Title at top: 'DIFFERENT GOAL, DIFFERENT CRITERIA'. In the "
              "centre: a navy mountain icon labelled 'GOAL: a winter hike' at "
              "the top. A navy arrow points down to three rounded rectangular "
              "labels: 'insulated jacket', 'waterproof boots', 'thermal flask'. "
              "Clean, consistent style with the previous slide.",
              "Animate: the GOAL mountain icon appears first, holds briefly, "
              "then the arrow draws down and the three new criterion labels "
              "appear from left to right. "),
    ],
    narration_script=(
        "To choose well, three ideas help. A goal is what we're trying to "
        "achieve. An option is one of the things we could pick. And a "
        "criterion is a reason to prefer one option over another. "
        "Here's the important link: the goal shapes the criteria. If the goal "
        "is a warm weekend trip, we look for warm clothes, a lightweight bag, "
        "good shoes. But change the goal to a winter hike, and the criteria "
        "change too: now we need insulated layers, waterproof boots, a thermal "
        "flask. Same person, different goal, different criteria."
    ),
)
