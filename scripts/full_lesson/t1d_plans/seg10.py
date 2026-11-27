"""Segment 10 — Post-selection metrics. T1d pattern (infographic only)."""
from scripts.full_lesson.t1d_runner import SegmentPlanV2, SubShot


PLAN = SegmentPlanV2(
    title="Seg 10: Post-selection metrics",
    output_name="t1d_seg10",
    sub_shots=[
        # BEAT 1 -- SET EXPECTATIONS BEFORE CHOOSING (dashboard)
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration=(
                "A good selection decision doesn't end when you pick -- it "
                "ends when you check."
            ),
            slide=(
                "Title at top in bold dark navy sans-serif: 'SET "
                "EXPECTATIONS BEFORE CHOOSING'. Centre: a simple dashboard "
                "panel outline (rounded rectangle) containing three empty "
                "placeholder slots for gauge/dial icons in a row, each "
                "labelled underneath (left to right): 'COST', "
                "'RELIABILITY', 'SATISFACTION'. No actual gauges or "
                "targets yet. Clean 16:9 landscape. Spell exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration="Did the choice actually deliver what we hoped for?",
            edit_instruction=(
                "Fill in all three gauge placeholders with navy gauge/dial "
                "icons. On each gauge, mark a target zone in soft green "
                "(no needle positions yet, just the target markers). Keep "
                "EVERYTHING ELSE exactly as is -- same title, same panel, "
                "same labels 'COST', 'RELIABILITY', 'SATISFACTION'. Spell "
                "exactly."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "Set the expectations first. Before you choose, write down "
                "what 'good' would look like -- cost, reliability, how "
                "satisfied you'd be."
            ),
            edit_instruction=(
                "Keep the slide exactly the same -- do not change anything. "
                "Preserve the title, panel, and three gauges with their "
                "target markers."
            ),
            slide="",
        ),

        # BEAT 2 -- THEN MEASURE THE RESULT (needles)
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration="Then after some time, compare.",
            slide=(
                "Title at top in bold dark navy sans-serif: 'THEN MEASURE "
                "THE RESULT'. Centre: the same three-gauge dashboard, now "
                "showing a navy needle on each gauge pointing to its "
                "actual reading. COST needle points slightly HIGHER than "
                "its target (in soft gray). RELIABILITY needle points IN "
                "the target green zone. SATISFACTION needle points IN the "
                "target green zone. Labels 'COST', 'RELIABILITY', "
                "'SATISFACTION' below their gauges. No caption yet. Clean "
                "16:9 landscape. Spell exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration="Two out of three landed in the green.",
            edit_instruction=(
                "Add a slate-gray caption below the dashboard: 'Two out "
                "of three landed in the green.' Keep EVERYTHING ELSE "
                "exactly as is -- same title, same gauges, same needles. "
                "Spell exactly."
            ),
            slide="",
        ),

        # BEAT 3 -- EXPECTED vs ACTUAL table
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration=(
                "Expected monthly cost versus actual. Expected battery "
                "life versus actual. Expected learning curve versus actual."
            ),
            slide=(
                "Title at top in bold dark navy sans-serif: 'EXPECTED vs "
                "ACTUAL'. Centre: a clean two-column table. Headers: "
                "'EXPECTED' (left) and 'ACTUAL' (right). Three data rows: "
                "'Monthly cost: 1,200 | 1,350', 'Battery life: 10h | "
                "11h', 'Learning curve: 2 weeks | 6 weeks'. Navy table "
                "outlines, clean sans-serif. Clean 16:9 landscape. Spell "
                "exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "Most of the time, you'll find most things landed close."
            ),
            edit_instruction=(
                "Keep the slide exactly the same -- do not change "
                "anything. Preserve the title and all three rows."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "Occasionally one will miss -- and that's where the real "
                "learning is."
            ),
            edit_instruction=(
                "Highlight the 'Learning curve' row (the last data row) "
                "with a soft-gray background to flag the gap. Keep "
                "EVERYTHING ELSE exactly as is -- same title, same table "
                "structure, same values. Spell exactly."
            ),
            slide="",
        ),

        # BEAT 4 -- REVIEW AND IMPROVE (circular arrow)
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration=(
                "The review loop is what makes the next decision better."
            ),
            slide=(
                "Title at top in bold dark navy sans-serif: 'REVIEW AND "
                "IMPROVE'. Centre: a circular arrow icon (review-loop "
                "symbol) in navy, with three labelled milestones along "
                "its circumference: 'CHOOSE' at top, 'MEASURE' at right, "
                "'ADJUST' at bottom. No caption yet. Clean 16:9 landscape. "
                "Spell exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration="The review is the real learning.",
            edit_instruction=(
                "Add a slate-gray caption below the loop: 'The review is "
                "the real learning.' Keep EVERYTHING ELSE exactly as is "
                "-- same title, same loop with its three milestones. "
                "Spell exactly."
            ),
            slide="",
        ),
    ],
)
