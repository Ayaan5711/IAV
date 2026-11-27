"""Segment 9 — Common decision mistakes. T1d pattern (infographic only)."""
from scripts.full_lesson.t1d_runner import SegmentPlanV2, SubShot


PLAN = SegmentPlanV2(
    title="Seg 9: Common decision mistakes",
    output_name="t1d_seg09",
    sub_shots=[
        # BEAT 1 -- FIVE COMMON MISTAKES (numbered list reveal)
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration="Five mistakes come up again and again.",
            slide=(
                "Title at top in bold dark navy sans-serif: 'FIVE COMMON "
                "MISTAKES'. Centre: five empty slate-gray placeholder "
                "rows stacked vertically, each with a navy circle numeral "
                "on the left (1 through 5) and a slate-gray dashed line "
                "where a label will go. Clean 16:9 landscape, generous "
                "spacing. Spell exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "Choosing by appearance alone -- picking the option that "
                "looks shiniest, not the one that actually fits."
            ),
            edit_instruction=(
                "Fill in the FIRST row (numeral '1') with the label "
                "'Choosing by appearance alone' in navy sans-serif. Keep "
                "EVERYTHING ELSE exactly as is -- same title, same four "
                "empty rows below. Spell exactly."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "Following what other people picked, when their situation "
                "isn't your situation."
            ),
            edit_instruction=(
                "Fill in the SECOND row (numeral '2') with the label "
                "'Following what others picked' in navy sans-serif. Keep "
                "EVERYTHING ELSE exactly as is. Spell exactly."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "Ignoring ongoing costs, the fuel and maintenance after the "
                "price tag."
            ),
            edit_instruction=(
                "Fill in the THIRD row (numeral '3') with the label "
                "'Ignoring ongoing costs' in navy sans-serif. Keep "
                "EVERYTHING ELSE exactly as is. Spell exactly."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "Using incomplete information, when a little more research "
                "would change the answer."
            ),
            edit_instruction=(
                "Fill in the FOURTH row (numeral '4') with the label "
                "'Using incomplete information' in navy sans-serif. Keep "
                "EVERYTHING ELSE exactly as is. Spell exactly."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "And the trickiest -- changing the criteria at the last "
                "moment to justify an option you already fell in love with."
            ),
            edit_instruction=(
                "Fill in the FIFTH row (numeral '5') with the label "
                "'Changing criteria to justify a favourite' in navy "
                "sans-serif. Keep EVERYTHING ELSE exactly as is. Spell "
                "exactly."
            ),
            slide="",
        ),

        # BEAT 2 -- THE ANTIDOTE
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration="The antidote is simple to state, harder to practice.",
            slide=(
                "Title at top in bold dark navy sans-serif: 'THE ANTIDOTE'. "
                "Centre: two rounded rectangular cards side by side. Left "
                "card has a navy checkmark icon at top and 'EVIDENCE' "
                "label underneath in bold sans-serif. Right card has a "
                "scale/gavel icon and 'CRITERIA SET IN ADVANCE' label "
                "underneath. No caption below yet. Clean 16:9 landscape. "
                "Spell exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration="Decide the rules before you decide the winner.",
            edit_instruction=(
                "Add a slate-gray caption spanning below both cards: "
                "'Decide the rules before you decide the winner.' Keep "
                "EVERYTHING ELSE exactly as is -- same title, same two "
                "cards with their icons and labels. Spell exactly."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "Agree on what matters -- the evidence you'll use, the "
                "criteria you'll weigh -- before you even look at the options."
            ),
            edit_instruction=(
                "Keep the slide exactly the same. Preserve the title, the "
                "two cards with their icons and labels, and the caption. "
                "No new text, no changes."
            ),
            slide="",
        ),
    ],
)
