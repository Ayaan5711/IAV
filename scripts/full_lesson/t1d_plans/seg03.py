"""Segment 3 — Need and constraints. T1d pattern (infographic only)."""
from scripts.full_lesson.t1d_runner import SegmentPlanV2, SubShot


PLAN = SegmentPlanV2(
    title="Seg 3: Need and constraints",
    output_name="t1d_seg03",
    sub_shots=[
        # BEAT 1 -- START WITH THE NEED
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration="Good selection starts with a clear need.",
            slide=(
                "Title at top in bold dark navy sans-serif: 'START WITH THE "
                "NEED'. Centre: one large rounded rectangle card in soft navy "
                "outline labelled 'THE NEED' at its top, empty inside (no "
                "caption yet). Clean 16:9 landscape. Spell every word exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration="What are we actually trying to get?",
            edit_instruction=(
                "Keep the slide exactly the same. Do not change anything -- "
                "same title, same empty 'THE NEED' card. No new text."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "Say we need a laptop for university coursework. That's the need."
            ),
            edit_instruction=(
                "Add a slate-gray caption inside the 'THE NEED' card reading "
                "'A laptop for university coursework.' Keep EVERYTHING ELSE "
                "exactly as is -- same title, same card outline. Spell exactly."
            ),
            slide="",
        ),

        # BEAT 2 -- THEN ADD THE CONSTRAINTS
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration=(
                "Then come the constraints. What's our budget?"
            ),
            slide=(
                "Title at top in bold dark navy sans-serif: 'THEN ADD THE "
                "CONSTRAINTS'. Centre: the 'THE NEED' card with its caption "
                "'A laptop for university coursework.' at the top. Below the "
                "need card, a single navy line connects down to a BUDGET "
                "constraint card labelled 'BUDGET: under 60,000'. Positions "
                "below that are placeholders for TIME and CONTEXT cards. "
                "Clean flat design. Spell every word exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration="When do we need it by?",
            edit_instruction=(
                "Add a second constraint card next to the BUDGET card, "
                "connected by a navy line to the NEED card. The new card is "
                "labelled 'TIME: needed by next month'. Keep EVERYTHING ELSE "
                "exactly as is -- same title, same NEED card with its "
                "caption, same BUDGET card. Spell exactly."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "What's the context -- will we share it with a sibling? "
                "These constraints shape which options are even worth looking at."
            ),
            edit_instruction=(
                "Add a third constraint card to the right of the TIME card, "
                "connected by a navy line to the NEED card. The new card is "
                "labelled 'CONTEXT: shared with sibling'. Keep EVERYTHING "
                "ELSE exactly as is. Spell exactly."
            ),
            slide="",
        ),

        # BEAT 3 -- SAME NEED, DIFFERENT PEOPLE
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration=(
                "And here's why constraints matter: the same need can suit "
                "two people very differently."
            ),
            slide=(
                "Title at top in bold dark navy sans-serif: 'SAME NEED, "
                "DIFFERENT PEOPLE'. Centre: two simple navy silhouette avatars "
                "side by side, each with a small empty thought bubble above. "
                "Below each silhouette a label: left 'STUDENT A', right "
                "'STUDENT B'. Thought bubbles are empty -- no content yet. "
                "Clean flat design. Spell every word exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "One student needs something light with long battery life "
                "for a daily commute."
            ),
            edit_instruction=(
                "Fill in Student A's thought bubble (the LEFT one) with a "
                "small laptop icon and the text chip 'light, long battery' in "
                "navy sans-serif. Keep EVERYTHING ELSE exactly as is -- same "
                "title, Student B's thought bubble still empty, same labels. "
                "Spell exactly."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "Another needs something powerful with a big screen for "
                "design work at home. Same need. Different constraints. "
                "Different right answers."
            ),
            edit_instruction=(
                "Fill in Student B's thought bubble (the RIGHT one) with a "
                "small laptop icon and the text chip 'powerful, big screen' "
                "in navy sans-serif. Keep EVERYTHING ELSE exactly as is. "
                "Spell exactly."
            ),
            slide="",
        ),
    ],
)
