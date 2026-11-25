"""Segment 8: Selection at life crossroads (10:00-11:30). ~40s."""
from iav.capabilities.video_hybrid_segment import SegmentPlan
from scripts.full_lesson._shared import veo, infog

PLAN = SegmentPlan(
    title="Seg 8: Life crossroads",
    beats=[
        veo(8,
            "A young adult in their early twenties stands on a quiet path at a "
            "fork in a park, looking thoughtfully at a wooden signpost with two "
            "arrow-shaped boards pointing in different directions. Soft golden "
            "evening light. Wide shot, contemplative mood, slow gentle motion. "
            "The signpost letters are indistinct."),
        infog(10,
              "Title at top in bold dark navy: 'BIG DECISIONS, SAME SHAPE'. "
              "Below, a simple branching tree diagram: a central node labelled "
              "'A CROSSROADS' sits at the top centre, with three navy lines "
              "diverging downward to three leaf labels: 'CAREER', 'EDUCATION', "
              "'RELOCATION'. Each leaf is a rounded rectangle. Clean flat "
              "design.",
              "Animate: the 'A CROSSROADS' node appears at the top first, then "
              "each branch line draws itself downward in sequence (left "
              "'CAREER' first, then centre 'EDUCATION', then right "
              "'RELOCATION'), with each leaf label fading in as its branch "
              "completes."),
        infog(10,
              "Title: 'THE DIMENSIONS SHIFT'. Centre: four columns arranged "
              "across the slide, each a small labelled bar group, headed by "
              "a single word in bold navy: 'INTERESTS', 'VALUES', "
              "'FEASIBILITY', 'GROWTH'. Each column has a soft-green bar of "
              "varying length showing how much it matters. Slate-gray caption "
              "underneath: 'Different from a purchase -- these matter more.'",
              "Animate: the four column labels appear first simultaneously, "
              "then each bar grows upward from the baseline to its respective "
              "height, in a staggered wave from left to right. The caption "
              "types in last."),
        infog(10,
              "Title: 'UNCERTAINTY AND REVERSIBILITY'. Two circular diagrams "
              "side by side in the centre. Left diagram has a 'LOCK' icon in "
              "its centre and is labelled 'HARD TO REVERSE' underneath in "
              "bold navy. Right diagram has a 'CIRCULAR ARROW' icon and is "
              "labelled 'EASY TO ADJUST' underneath. Slate-gray caption "
              "below both: 'Weigh how much a wrong move will cost to undo.'",
              "Animate: the two circular diagrams fade in side by side, left "
              "first with the lock icon, then right with the circular arrow "
              "icon. Each label appears beneath its respective diagram. "
              "Caption types in last."),
    ],
    narration_script=(
        "Big life decisions -- a career choice, picking a course of study, "
        "relocating to a new city -- have the same shape as everyday "
        "choices. A goal. Alternatives. Criteria. "
        "But the dimensions are different. We weigh interests. We weigh "
        "values. We weigh feasibility. We weigh how much the choice sets up "
        "the next few years of growth. "
        "And one dimension you don't usually think about when buying "
        "cookies: how hard is this to reverse? A rental is easy to undo. A "
        "house purchase is harder. Marriage, harder still. Factor in "
        "reversibility: the less reversible, the more care the decision "
        "deserves upfront."
    ),
)
