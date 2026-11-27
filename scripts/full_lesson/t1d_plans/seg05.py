"""Segment 5 — Hard and soft criteria. T1d pattern (infographic only)."""
from scripts.full_lesson.t1d_runner import SegmentPlanV2, SubShot


PLAN = SegmentPlanV2(
    title="Seg 5: Hard and soft criteria",
    output_name="t1d_seg05",
    sub_shots=[
        # BEAT 1 -- HARD CRITERIA (ruler)
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration=(
                "Not every criterion is measured the same way. Some are hard "
                "criteria -- things we can verify objectively."
            ),
            slide=(
                "Title at top in bold dark navy sans-serif: 'HARD CRITERIA'. "
                "Centre: a clean illustrated measuring tape or ruler icon in "
                "navy. Short slate-gray caption underneath: 'Objectively "
                "verifiable -- the number is the number.' No example chips "
                "yet. Clean 16:9 landscape. Spell exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "Price is a number. Weight is a number. Either the laptop "
                "fits in your bag or it doesn't."
            ),
            edit_instruction=(
                "Add two example chips on either side of the ruler icon: a "
                "chip labelled 'PRICE' on the left, a chip labelled 'WEIGHT' "
                "on the right, both in clean navy sans-serif. Keep "
                "EVERYTHING ELSE exactly as is -- same title, same ruler, "
                "same caption. Spell exactly."
            ),
            slide="",
        ),

        # BEAT 2 -- SOFT CRITERIA (thinking face)
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration=(
                "Others are soft criteria. Comfort. Style. The right feel."
            ),
            slide=(
                "Title at top in bold dark navy sans-serif: 'SOFT CRITERIA'. "
                "Centre: a simple navy-outline illustrated face icon with a "
                "thinking expression. Short slate-gray caption underneath: "
                "'Judgement call -- depends on the person.' No chips yet. "
                "Consistent flat design with the previous slide. Spell exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "These are judgement calls -- what works for one person "
                "might not work for another."
            ),
            edit_instruction=(
                "Add two example chips on either side of the thinking face "
                "icon: a chip labelled 'COMFORT' on the left, a chip "
                "labelled 'STYLE' on the right, both in clean navy "
                "sans-serif. Keep EVERYTHING ELSE exactly as is -- same "
                "title, same face, same caption. Spell exactly."
            ),
            slide="",
        ),

        # BEAT 3 -- TWO SEPARATE QUESTIONS (grid empty, then populated)
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration=(
                "Here's the subtlety worth remembering: hard versus soft is "
                "one question."
            ),
            slide=(
                "Title at top in bold dark navy sans-serif: 'TWO SEPARATE "
                "QUESTIONS'. Centre: a clean empty 2x2 grid (just the axis "
                "lines and quadrant boundaries). Vertical axis labelled "
                "'IMPORTANCE' with an arrow pointing up on the left. "
                "Horizontal axis has 'OBJECTIVE' on the left end and "
                "'SUBJECTIVE' on the right end. No chips in the quadrants "
                "yet. Clean 16:9 landscape. Spell exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "Important versus less important is a completely separate question."
            ),
            edit_instruction=(
                "Keep the 2x2 grid exactly the same. Do NOT populate any "
                "quadrant yet. Add a small slate-gray annotation somewhere "
                "harmless indicating that this is about two axes. (You may "
                "simply not add anything -- preserve the slide.) Keep "
                "EVERYTHING ELSE exactly as is."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "A measurable feature like fuel efficiency might be only "
                "mildly important,"
            ),
            edit_instruction=(
                "Populate TWO of the four quadrants: upper-left with a "
                "soft-green chip labelled 'PRICE' (important + objective); "
                "lower-left with a soft-gray chip labelled 'FUEL EFFICIENCY' "
                "(less important + objective). Right side (subjective) "
                "quadrants remain empty. Keep EVERYTHING ELSE exactly as is "
                "-- same title, same axes. Spell exactly."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "while a judgement call like comfort might be the deciding "
                "factor. Keep the two questions apart."
            ),
            edit_instruction=(
                "Populate the remaining TWO quadrants: upper-right with a "
                "soft-green chip labelled 'COMFORT' (important + "
                "subjective); lower-right with a soft-gray chip labelled "
                "'COLOR' (less important + subjective). Keep EVERYTHING "
                "ELSE exactly as is. Spell exactly."
            ),
            slide="",
        ),
    ],
)
