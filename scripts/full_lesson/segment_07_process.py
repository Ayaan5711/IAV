"""Segment 7: A structured selection process (8:30-10:00). ~40s."""
from iav.capabilities.video_hybrid_segment import SegmentPlan
from scripts.full_lesson._shared import veo, infog

PLAN = SegmentPlan(
    title="Seg 7: Structured selection process",
    beats=[
        infog(10,
              "Title at top in bold dark navy: 'A STRUCTURED PROCESS'. Below "
              "the title, a clean numbered vertical list of five steps in soft "
              "navy sans-serif: '1. Define the goal', '2. List the criteria', "
              "'3. Gather evidence', '4. Filter by essentials', '5. Compare "
              "what's left'. Each step on its own line, generous spacing "
              "between them, each with a small navy circle numeral on the left.",
              "Animate: the title appears first, then each numbered step fades "
              "in from left to right one after the other, in sequence 1 "
              "through 5, with a short pause between each. Final state: all "
              "five steps visible in a clean list."),
        infog(10,
              "Title: 'BUILD A COMPARISON MATRIX'. A simple 3-column by "
              "4-row table in the centre. Column headers: 'CRITERION' (left), "
              "'OPTION A' (middle), 'OPTION B' (right). Row labels in the "
              "first column: 'Price', 'Battery', 'Weight', 'Build quality'. "
              "The data cells are empty for now. Navy table outlines, clean "
              "sans-serif.",
              "Animate: the table outline draws itself in first (headers "
              "appearing in sequence left-to-right, then horizontal row "
              "separators appearing top-to-bottom). The four criterion labels "
              "in the first column appear one by one, top to bottom."),
        infog(10,
              "Title: 'BUILD A COMPARISON MATRIX'. The same 3-column by "
              "4-row table from before, now with cells populated. Row by row: "
              "'Price' row: '55,000' in Option A column, '62,000' in Option B "
              "column. 'Battery' row: '8h', '12h'. 'Weight' row: '1.6kg', "
              "'1.9kg'. 'Build quality' row: 'Good', 'Excellent'. Numbers in "
              "clean navy sans-serif.",
              "Animate: starting from the empty table (headers and criterion "
              "labels visible), each data cell populates in sequence -- "
              "complete Option A column first (top to bottom), then Option B "
              "column (top to bottom)."),
        infog(10,
              "Title: 'WEIGH BY WHAT MATTERS'. The same comparison matrix, "
              "but now a fourth column has been added on the right labelled "
              "'WEIGHT' with values down the column: 'Price: 3', 'Battery: "
              "5', 'Weight: 2', 'Build quality: 4'. The 'Battery' row is "
              "highlighted in soft green to show it has the highest weight.",
              "Animate: a new rightmost column labelled 'WEIGHT' slides in "
              "from the right edge, its values appear top to bottom, then "
              "the 'Battery' row gently highlights in soft green to show it "
              "as the highest-weighted criterion."),
    ],
    narration_script=(
        "Here's a clean process for a selection decision. Five steps. "
        "First, define the goal clearly. Second, list the criteria that "
        "connect to the goal. Third, gather real evidence for each option "
        "against those criteria. Fourth, filter out anything that fails an "
        "essential requirement. Fifth, compare what's left. "
        "A comparison matrix helps at step five. Put the criteria down the "
        "side, the options across the top, and fill in what you know. Then "
        "weight each criterion by how much it matters -- here, battery life "
        "carries the most weight, so the option that wins on battery is "
        "likely the right call, even if another option edges it out "
        "elsewhere."
    ),
)
