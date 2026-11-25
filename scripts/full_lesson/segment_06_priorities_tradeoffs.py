"""Segment 6: Priorities and trade-offs (7:00-8:30). ~40s."""
from iav.capabilities.video_hybrid_segment import SegmentPlan
from scripts.full_lesson._shared import infog

PLAN = SegmentPlan(
    title="Seg 6: Priorities and trade-offs",
    beats=[
        infog(10,
              "Title at top in bold dark navy: 'NO OPTION WINS ON EVERYTHING'. "
              "Below, a clean illustrated balance scale (two pans suspended "
              "from a central beam, in simple navy line art). Left pan has a "
              "small label 'OPTION A', right pan has a small label 'OPTION B'. "
              "Both pans empty for now.",
              "Animate: the balance scale appears centred and level. Then a "
              "small 'PRICE' chip lands in the left pan (A) making it tip "
              "slightly down. Then a small 'QUALITY' chip lands in the right "
              "pan (B) making it tip the other way. The scale oscillates "
              "gently and settles tilted toward whichever side has the "
              "heavier chip."),
        infog(10,
              "Title: 'PRIORITIES SHIFT THE BALANCE'. The same balance scale "
              "from before. A small navy weight icon labelled 'BUDGET IS "
              "TIGHT' sits prominently above the left pan ('OPTION A' side). "
              "The left pan is visibly lower, tilted down. Caption underneath "
              "in slate-gray: 'When budget matters most, the cheaper option "
              "wins.'",
              "Animate: the weight icon labelled 'BUDGET IS TIGHT' fades in "
              "above the left pan and 'drops' onto it, making the balance "
              "tip clearly to the left. The caption types in character by "
              "character beneath the scale."),
        infog(10,
              "Title: 'PRIORITY BARS'. A clean vertical bar chart "
              "visualization in the centre: four horizontal rows, each row is "
              "a labelled priority bar. From top to bottom: "
              "'AFFORDABILITY' with a long green bar filling most of the row, "
              "'CONVENIENCE' with a medium-length bar, 'QUALITY' with a "
              "shorter bar, 'STYLE' with a very short bar. All bars on the "
              "same baseline. Soft navy labels, soft green fills, slate-gray "
              "neutral.",
              "Animate: all four labels appear first, then each horizontal "
              "bar grows from zero to its full length from left to right, in "
              "order from top (longest) to bottom (shortest)."),
        infog(10,
              "Title: 'SAME PERSON, NEW SITUATION'. The same four-row "
              "priority chart from before, but now the bar lengths have "
              "shifted: 'AFFORDABILITY' is now a short bar, 'CONVENIENCE' is "
              "medium, 'QUALITY' is a long green bar, 'STYLE' is medium. The "
              "re-ordering reflects a life change (e.g., a job promotion).",
              "Animate: starting from the previous arrangement (affordability "
              "longest), each bar smoothly animates to its new length -- "
              "affordability shrinks, quality grows to become the longest. "
              "Convention: bars animate simultaneously."),
    ],
    narration_script=(
        "Rarely does one option win on everything. One is cheaper. Another is "
        "higher quality. A third is more convenient. We have to balance. "
        "What tips the balance is our priorities. If budget is tight, "
        "affordability outweighs everything else. If the budget loosens, we "
        "can afford to care more about quality or style. "
        "And priorities change. The person who ranked affordability first "
        "last year may rank quality first this year, after a job change or a "
        "family change. Same person, same framework, new ranking. That's "
        "normal. Revisit the priorities when the situation changes."
    ),
)
