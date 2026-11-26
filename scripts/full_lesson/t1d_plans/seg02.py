"""Segment 2 — Goal, Option, Criterion. Validated under T1d."""
from scripts.full_lesson.t1d_runner import SegmentPlanV2, SubShot


PLAN = SegmentPlanV2(
    title="Seg 2: Goal, option, criterion",
    output_name="t1d_seg02",
    sub_shots=[
        # BEAT 1 -- 'GOAL, OPTION, CRITERION' three cards reveal
        SubShot(
            is_beat_start=True,
            narration="To choose well, three ideas help.",
            slide=(
                "Title at top in bold dark navy sans-serif: 'GOAL, OPTION, "
                "CRITERION'. Below the title, three rounded rectangular card "
                "OUTLINES side-by-side (just the outlines, empty inside, in soft "
                "slate-gray). Clean 16:9 landscape layout, generous white space. "
                "No labels inside the cards yet. Spell every word exactly, no typos."
            ),
        ),
        SubShot(
            is_beat_start=False,
            narration="A goal is what we're trying to achieve.",
            edit_instruction=(
                "Fill in the LEFT card with a navy background, a white star icon, "
                "and the word 'GOAL' in white bold sans-serif centered inside the "
                "card. Keep EVERYTHING ELSE in the image exactly as is -- same "
                "title, same centre and right outlines, same layout, same "
                "background. Only the left card changes. Spell 'GOAL' exactly."
            ),
            slide="",
        ),
        SubShot(
            is_beat_start=False,
            narration="An option is one of the things we could pick.",
            edit_instruction=(
                "Fill in the CENTRE card with a navy background, a white circle "
                "icon, and the word 'OPTION' in white bold sans-serif centered "
                "inside the card. Keep EVERYTHING ELSE in the image exactly as is "
                "-- same title, same left card (GOAL), same right outline. Only "
                "the centre card changes. Spell 'OPTION' exactly."
            ),
            slide="",
        ),
        SubShot(
            is_beat_start=False,
            narration="And a criterion is a reason to prefer one option over another.",
            edit_instruction=(
                "Fill in the RIGHT card with a navy background, a white checkmark "
                "icon, and the word 'CRITERION' in white bold sans-serif centered "
                "inside the card. Keep EVERYTHING ELSE in the image exactly as is "
                "-- same title, same left card (GOAL), same centre card (OPTION). "
                "Only the right card changes. Spell 'CRITERION' exactly."
            ),
            slide="",
        ),

        # BEAT 2 -- 'THE GOAL SHAPES THE CRITERIA' (warm weekend trip)
        SubShot(
            is_beat_start=True,
            narration="Here's the important link: the goal shapes the criteria.",
            slide=(
                "Title at top in bold dark navy: 'THE GOAL SHAPES THE CRITERIA'. "
                "In the centre near the top, a navy star icon sits alone. Below "
                "the star, a navy arrow points downward. Below the arrow, three "
                "slate-gray empty rounded rectangular label outlines are in a "
                "row, placeholders. Clean 16:9 landscape, navy on white. Spell "
                "every word exactly."
            ),
        ),
        SubShot(
            is_beat_start=False,
            narration="If the goal is a warm weekend trip,",
            edit_instruction=(
                "Add the label 'GOAL: a warm weekend trip' in navy sans-serif, "
                "placed immediately next to or just below the star icon, so it "
                "reads as the star's caption. Keep EVERYTHING ELSE in the image "
                "exactly the same -- same title, same arrow, same three empty "
                "label outlines below. Spell 'GOAL: a warm weekend trip' exactly."
            ),
            slide="",
        ),
        SubShot(
            is_beat_start=False,
            narration="we look for warm clothes, a lightweight bag, good shoes.",
            edit_instruction=(
                "Fill in the three label outlines in the bottom row left-to-right "
                "with these navy sans-serif labels: 'warm clothes', 'lightweight "
                "bag', 'good shoes'. Keep EVERYTHING ELSE in the image exactly "
                "the same -- same title, same star with its GOAL caption, same "
                "arrow. Spell every word exactly."
            ),
            slide="",
        ),

        # BEAT 3 -- 'DIFFERENT GOAL, DIFFERENT CRITERIA' (winter hike)
        SubShot(
            is_beat_start=True,
            narration="But change the goal to a winter hike,",
            slide=(
                "Title at top in bold dark navy: 'DIFFERENT GOAL, DIFFERENT "
                "CRITERIA'. Centre: a navy mountain peak icon near the top, with "
                "the label 'GOAL: a winter hike' in navy sans-serif just next to "
                "or below it. A navy arrow points downward from the icon. Below "
                "the arrow, three slate-gray empty rounded rectangular label "
                "outlines are in a row, placeholders. Clean 16:9 landscape, "
                "consistent style with the previous slide. Spell exactly."
            ),
        ),
        SubShot(
            is_beat_start=False,
            narration=(
                "and the criteria change too: now we need insulated layers, "
                "waterproof boots, a thermal flask."
            ),
            edit_instruction=(
                "Fill in the three label outlines in the bottom row left-to-right "
                "with these navy sans-serif labels: 'insulated layers', "
                "'waterproof boots', 'thermal flask'. Keep EVERYTHING ELSE "
                "exactly the same -- same title, same mountain with its GOAL "
                "caption, same arrow. Spell every word exactly."
            ),
            slide="",
        ),
        SubShot(
            is_beat_start=False,
            narration="Same person, different goal, different criteria.",
            edit_instruction=(
                "Add a subtle soft-green outline/glow around the full composition "
                "(the mountain icon with its GOAL caption, the arrow, and the row "
                "of three labels) to emphasise the whole structure as one unit. "
                "Keep EVERYTHING ELSE in the image exactly the same. Do not add "
                "any new text."
            ),
            slide="",
        ),
    ],
)
