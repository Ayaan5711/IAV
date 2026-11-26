"""Segment 7 — A structured selection process. Validated under T1d."""
from scripts.full_lesson.t1d_runner import SegmentPlanV2, SubShot


PLAN = SegmentPlanV2(
    title="Seg 7: Structured selection process",
    output_name="t1d_seg07",
    sub_shots=[
        # BEAT 1 -- 'A STRUCTURED PROCESS' 5-step list reveal
        SubShot(
            is_beat_start=True,
            narration="Here's a clean process for a selection decision. Five steps.",
            slide=(
                "Title at top in bold dark navy sans-serif: 'A STRUCTURED "
                "PROCESS'. Centre: five empty slate-gray placeholder rows "
                "stacked vertically, each with a small navy circle numeral on "
                "the left (1 through 5 top to bottom) and a slate-gray dashed "
                "line where a label will go. Clean 16:9 landscape, generous "
                "spacing. Spell every word exactly."
            ),
        ),
        SubShot(
            is_beat_start=False,
            narration="First, define the goal clearly.",
            edit_instruction=(
                "Fill in the first row (next to numeral '1') with the label "
                "'Define the goal' in navy sans-serif. Keep EVERYTHING ELSE "
                "exactly as is -- same title, same numerals, same four empty "
                "rows below. Spell 'Define the goal' exactly."
            ),
            slide="",
        ),
        SubShot(
            is_beat_start=False,
            narration="Second, list the criteria that connect to the goal.",
            edit_instruction=(
                "Fill in the second row (next to numeral '2') with the label "
                "'List the criteria' in navy sans-serif. Keep EVERYTHING ELSE "
                "exactly as is -- same title, numerals, row 1 ('Define the "
                "goal'), and three empty rows below. Spell exactly."
            ),
            slide="",
        ),
        SubShot(
            is_beat_start=False,
            narration="Third, gather real evidence for each option against those criteria.",
            edit_instruction=(
                "Fill in the third row (next to numeral '3') with the label "
                "'Gather evidence' in navy sans-serif. Keep EVERYTHING ELSE "
                "exactly as is. Spell exactly."
            ),
            slide="",
        ),
        SubShot(
            is_beat_start=False,
            narration="Fourth, filter out anything that fails an essential requirement.",
            edit_instruction=(
                "Fill in the fourth row (next to numeral '4') with the label "
                "'Filter by essentials' in navy sans-serif. Keep EVERYTHING "
                "ELSE exactly as is. Spell exactly."
            ),
            slide="",
        ),
        SubShot(
            is_beat_start=False,
            narration="Fifth, compare what's left.",
            edit_instruction=(
                "Fill in the fifth row (next to numeral '5') with the label "
                "'Compare what's left' in navy sans-serif. Keep EVERYTHING "
                "ELSE exactly as is. Spell exactly."
            ),
            slide="",
        ),

        # BEAT 2 -- 'BUILD A COMPARISON MATRIX' (empty table)
        SubShot(
            is_beat_start=True,
            narration=(
                "A comparison matrix helps at step five. Put the criteria down "
                "the side, and the options across the top."
            ),
            slide=(
                "Title at top in bold dark navy: 'BUILD A COMPARISON MATRIX'. "
                "Centre: a clean 3-column by 5-row table in navy outlines. Top "
                "row (headers): leftmost cell says 'CRITERION', middle says "
                "'OPTION A', right says 'OPTION B'. First-column row labels "
                "under the header: 'Price', 'Battery', 'Weight', 'Build "
                "quality' (one per row). All data cells (right 2 columns, rows "
                "2-5) are empty. Clean sans-serif. Spell every word exactly."
            ),
        ),

        # BEAT 3 -- Fill the comparison matrix
        SubShot(
            is_beat_start=True,
            narration="And fill in what you know about each option.",
            slide=(
                "Same comparison matrix as before but now the data cells are "
                "populated. Title at top in bold dark navy: 'BUILD A "
                "COMPARISON MATRIX'. Table rows (with 'CRITERION', 'OPTION A', "
                "'OPTION B' headers): 'Price' row: 55,000 | 62,000. 'Battery' "
                "row: 8h | 12h. 'Weight' row: 1.6kg | 1.9kg. 'Build quality' "
                "row: Good | Excellent. Numbers and labels in navy sans-serif. "
                "Spell every word exactly."
            ),
        ),

        # BEAT 4 -- 'WEIGH BY WHAT MATTERS' with highlighted winner
        SubShot(
            is_beat_start=True,
            narration="Then weight each criterion by how much it matters.",
            slide=(
                "Same comparison matrix as the populated version, but now a "
                "FOURTH column has been added on the right labelled 'WEIGHT' "
                "in bold navy. Weight column values top to bottom: 3, 5, 2, 4 "
                "(matching rows Price, Battery, Weight, Build quality). Title "
                "at top: 'WEIGH BY WHAT MATTERS'. Clean navy on white, 16:9 "
                "landscape. Spell every word exactly."
            ),
        ),
        SubShot(
            is_beat_start=False,
            narration="Here, battery life carries the most weight.",
            edit_instruction=(
                "Highlight the entire 'Battery' row (the row with values 8h | "
                "12h | 5) in soft-green background to emphasise it as the "
                "highest-weighted criterion. Keep EVERYTHING ELSE exactly as "
                "is -- same title, same table structure, same values."
            ),
            slide="",
        ),
        SubShot(
            is_beat_start=False,
            narration=(
                "So the option that wins on battery is likely the right call, "
                "even if another option edges it out elsewhere."
            ),
            edit_instruction=(
                "Draw a soft-green outlined box around the single cell "
                "containing '12h' in the Battery row (Option B's battery). "
                "Keep the soft-green row highlight on the Battery row and "
                "everything else exactly as is. This marks Option B's battery "
                "value as the winner."
            ),
            slide="",
        ),
    ],
)
