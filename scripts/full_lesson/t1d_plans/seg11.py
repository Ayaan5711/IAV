"""Segment 11 — Recap: choose, measure, improve. Validated under T1d."""
from scripts.full_lesson.t1d_runner import SegmentPlanV2, SubShot


PLAN = SegmentPlanV2(
    title="Seg 11: Recap",
    output_name="t1d_seg11",
    sub_shots=[
        # BEAT 1 -- 'THE FRAMEWORK' 5-item checklist
        SubShot(
            is_beat_start=True,
            narration="Let's pull it together.",
            slide=(
                "Title at top in large bold dark navy sans-serif: 'THE "
                "FRAMEWORK'. Centre: five empty placeholder checklist rows "
                "stacked vertically, each with a slate-gray empty checkmark "
                "square on the left (position marker) and a slate-gray dashed "
                "line where a label will go. Clean 16:9 landscape, generous "
                "spacing. Spell every word exactly."
            ),
        ),
        SubShot(
            is_beat_start=False,
            narration="Clarify the goal.",
            edit_instruction=(
                "Fill in the FIRST checklist row: replace the slate-gray empty "
                "square with a soft-green checkmark and fill the dashed line "
                "with the label 'Clarify the goal' in navy sans-serif. Keep "
                "EVERYTHING ELSE exactly as is -- same title, same four empty "
                "rows below. Spell exactly."
            ),
            slide="",
        ),
        SubShot(
            is_beat_start=False,
            narration="Separate what's essential from what's merely desirable.",
            edit_instruction=(
                "Fill in the SECOND checklist row: replace the slate-gray "
                "empty square with a soft-green checkmark and fill the dashed "
                "line with the label 'Separate essential from desirable' in "
                "navy sans-serif. Keep EVERYTHING ELSE exactly as is."
            ),
            slide="",
        ),
        SubShot(
            is_beat_start=False,
            narration="Weigh the evidence, not the impression.",
            edit_instruction=(
                "Fill in the THIRD checklist row: replace the slate-gray empty "
                "square with a soft-green checkmark and fill the dashed line "
                "with the label 'Weigh evidence' in navy sans-serif. Keep "
                "EVERYTHING ELSE exactly as is."
            ),
            slide="",
        ),
        SubShot(
            is_beat_start=False,
            narration="Compare the real trade-offs.",
            edit_instruction=(
                "Fill in the FOURTH checklist row: replace the slate-gray "
                "empty square with a soft-green checkmark and fill the dashed "
                "line with the label 'Compare trade-offs' in navy sans-serif. "
                "Keep EVERYTHING ELSE exactly as is."
            ),
            slide="",
        ),
        SubShot(
            is_beat_start=False,
            narration="And review the result, so the next decision is a better one.",
            edit_instruction=(
                "Fill in the FIFTH checklist row: replace the slate-gray empty "
                "square with a soft-green checkmark and fill the dashed line "
                "with the label 'Review the result' in navy sans-serif. Keep "
                "EVERYTHING ELSE exactly as is."
            ),
            slide="",
        ),

        # BEAT 2 -- 'CHOOSE, MEASURE, IMPROVE' three badges + loop
        SubShot(
            is_beat_start=True,
            narration="Choose, measure, improve.",
            slide=(
                "Title at top in bold dark navy: 'CHOOSE, MEASURE, IMPROVE'. "
                "Centre: three large navy circular badges in a row across the "
                "middle. Left badge: filled navy with a white target icon and "
                "the word 'CHOOSE' underneath in bold navy sans-serif. Middle "
                "badge: slate-gray empty outline (placeholder) with no label. "
                "Right badge: slate-gray empty outline (placeholder) with no "
                "label. No arrows between them yet. Clean 16:9 landscape. "
                "Spell every word exactly."
            ),
        ),
        SubShot(
            is_beat_start=False,
            narration="That's the whole thing.",
            edit_instruction=(
                "Fill in the MIDDLE badge: replace the slate-gray outline with "
                "a filled navy circle, add a white gauge icon inside, and add "
                "'MEASURE' in bold navy sans-serif underneath. Also draw a "
                "navy arrow pointing from the CHOOSE badge to the MEASURE "
                "badge. Keep EVERYTHING ELSE exactly as is -- same title, "
                "same CHOOSE badge on the left, same empty right badge."
            ),
            slide="",
        ),
        SubShot(
            is_beat_start=False,
            narration="A loop, not a line.",
            edit_instruction=(
                "Fill in the RIGHT badge: replace the slate-gray outline with "
                "a filled navy circle, add a white upward-arrow icon inside, "
                "and add 'IMPROVE' in bold navy sans-serif underneath. Draw a "
                "navy arrow pointing from MEASURE to IMPROVE. Also draw a "
                "DASHED navy arrow curving from IMPROVE back to CHOOSE, "
                "closing the loop. Keep EVERYTHING ELSE exactly as is."
            ),
            slide="",
        ),
        SubShot(
            is_beat_start=False,
            narration=(
                "You don't just make decisions -- you learn to make them "
                "better. One at a time."
            ),
            edit_instruction=(
                "Add a caption underneath the three-badge-loop composition, "
                "in slate-gray sans-serif, that reads 'The framework is a "
                "loop, not a line.'. Keep EVERYTHING ELSE exactly as is -- "
                "same title, same three badges, same arrows."
            ),
            slide="",
        ),
    ],
)
