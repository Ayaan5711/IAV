"""Segment 10: Post-selection performance metrics (12:45-14:15). ~40s."""
from iav.capabilities.video_hybrid_segment import SegmentPlan
from scripts.full_lesson._shared import infog

PLAN = SegmentPlan(
    title="Seg 10: Post-selection metrics",
    beats=[
        infog(10,
              "Title at top in bold dark navy: 'SET EXPECTATIONS BEFORE "
              "CHOOSING'. Centre: a simple 'dashboard panel' illustration -- "
              "a rounded rectangle containing three gauge/dial icons in a "
              "row, each labelled underneath: 'COST', 'RELIABILITY', "
              "'SATISFACTION'. Each gauge has a target zone marked in soft "
              "green. Clean flat design.",
              "Animate: the dashboard panel outline appears first, then each "
              "of the three gauges inside fades in one by one from left to "
              "right (COST, RELIABILITY, SATISFACTION). A small target "
              "marker arrives on each gauge's green zone."),
        infog(10,
              "Title: 'THEN MEASURE THE RESULT'. The same three-gauge "
              "dashboard, now showing actual readings as a small navy "
              "arrow/needle pointing within each gauge. COST gauge needle "
              "points slightly higher than its target (in soft gray). "
              "RELIABILITY gauge needle points in the target zone (in soft "
              "green). SATISFACTION gauge needle points at target (in soft "
              "green). Caption underneath in slate-gray: 'Two out of three "
              "landed in the green.'",
              "Animate: starting from the empty gauges with just targets "
              "visible, the needle on each gauge sweeps from zero to its "
              "final reading in sequence: COST first, then RELIABILITY, "
              "then SATISFACTION. The caption types in last."),
        infog(10,
              "Title: 'EXPECTED vs ACTUAL'. A clean two-column labelled "
              "table in the centre. Left column header 'EXPECTED', right "
              "column header 'ACTUAL'. Rows: 'Monthly cost: 1,200 | 1,350', "
              "'Battery life: 10h | 11h', 'Learning curve: 2 weeks | 6 "
              "weeks'. The last row ('Learning curve') is highlighted in "
              "soft gray to flag a gap.",
              "Animate: the table outline appears first with its two column "
              "headers, then each row populates left-to-right in sequence "
              "(expected value first, then actual value). The 'Learning "
              "curve' row then gently highlights in soft gray at the end."),
        infog(10,
              "Title: 'REVIEW AND IMPROVE'. Centre: a circular arrow icon "
              "(the universal 'review loop' symbol) with three labelled "
              "milestones along its circumference: 'CHOOSE' (top), "
              "'MEASURE' (right), 'ADJUST' (bottom). Clean navy on white. "
              "Caption below: 'The review is the real learning.'",
              "Animate: the circular arrow draws itself clockwise starting "
              "from the top. As the arrow passes each milestone label, that "
              "label fades in: CHOOSE first (top), then MEASURE (right), "
              "then ADJUST (bottom). The caption types in last."),
    ],
    narration_script=(
        "A good selection decision doesn't end when you pick -- it ends "
        "when you check. Did the choice actually deliver what we hoped for? "
        "Set the expectations first. Before you choose, write down what "
        "'good' would look like -- cost, reliability, how satisfied you'd "
        "be. "
        "Then after some time, compare. Expected monthly cost versus actual. "
        "Expected battery life versus actual. Expected learning curve versus "
        "actual. Most of the time, you'll find most things landed close. "
        "Occasionally one will miss -- and that's where the real learning "
        "is. The review loop is what makes the next decision better."
    ),
)
