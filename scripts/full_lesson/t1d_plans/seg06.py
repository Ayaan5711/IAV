"""Segment 6 — Priorities and trade-offs. T1d pattern (infographic only)."""
from scripts.full_lesson.t1d_runner import SegmentPlanV2, SubShot


PLAN = SegmentPlanV2(
    title="Seg 6: Priorities and trade-offs",
    output_name="t1d_seg06",
    sub_shots=[
        # BEAT 1 -- NO OPTION WINS ON EVERYTHING (balance)
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration=(
                "Rarely does one option win on everything. One is cheaper. "
                "Another is higher quality. A third is more convenient."
            ),
            slide=(
                "Title at top in bold dark navy sans-serif: 'NO OPTION WINS "
                "ON EVERYTHING'. Centre: a clean illustrated balance scale "
                "in navy line art -- two pans suspended from a central "
                "beam, level. Left pan labelled 'OPTION A', right pan "
                "labelled 'OPTION B'. Both pans empty. Clean 16:9 "
                "landscape. Spell exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration="We have to balance.",
            edit_instruction=(
                "Add a 'PRICE' chip into the LEFT pan (Option A) and a "
                "'QUALITY' chip into the RIGHT pan (Option B). The balance "
                "is now slightly tilted (whichever chip visually looks "
                "heavier). Keep EVERYTHING ELSE exactly as is -- same "
                "title, same scale structure, same pan labels. Spell "
                "exactly."
            ),
            slide="",
        ),

        # BEAT 2 -- PRIORITIES SHIFT THE BALANCE
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration="What tips the balance is our priorities.",
            slide=(
                "Title at top in bold dark navy sans-serif: 'PRIORITIES "
                "SHIFT THE BALANCE'. Centre: the same balance scale -- left "
                "pan 'OPTION A' with a 'PRICE' chip, right pan 'OPTION B' "
                "with a 'QUALITY' chip. Scale level or slightly tilted. No "
                "additional weight icon yet. Clean 16:9 landscape. Spell "
                "exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "If budget is tight, affordability outweighs everything else."
            ),
            edit_instruction=(
                "Add a navy weight-shaped icon labelled 'BUDGET IS TIGHT' "
                "above the LEFT pan ('OPTION A'). The left pan is now "
                "visibly LOWER than the right, tipping the balance clearly "
                "to the left. Add a slate-gray caption below the scale: "
                "'When budget matters most, the cheaper option wins.' Keep "
                "EVERYTHING ELSE exactly as is -- same title, same pan "
                "labels, same original chips. Spell exactly."
            ),
            slide="",
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "If the budget loosens, we can afford to care more about "
                "quality or style."
            ),
            edit_instruction=(
                "Replace the 'BUDGET IS TIGHT' weight icon above the left "
                "pan with a 'BUDGET LOOSENS' icon above the RIGHT pan "
                "('OPTION B'). Now the right pan is visibly LOWER. Update "
                "the caption below the scale to read 'When budget loosens, "
                "quality or style can take the lead.' Keep EVERYTHING ELSE "
                "exactly as is. Spell exactly."
            ),
            slide="",
        ),

        # BEAT 3 -- PRIORITY BARS
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration=(
                "And priorities change. The person who ranked affordability "
                "first last year may rank quality first this year."
            ),
            slide=(
                "Title at top in bold dark navy sans-serif: 'PRIORITY "
                "BARS'. Centre: a clean horizontal-bar chart with four "
                "rows, top to bottom labelled: 'AFFORDABILITY', "
                "'CONVENIENCE', 'QUALITY', 'STYLE'. From top to bottom the "
                "bars are: long soft-green bar, medium bar, short bar, "
                "very short bar. All bars on the same left baseline. "
                "Clean 16:9 landscape. Spell exactly."
            ),
        ),

        # BEAT 4 -- SAME PERSON, NEW SITUATION (reordered bars)
        SubShot(
            kind="infographic",
            is_beat_start=True,
            narration=(
                "After a job change or a family change."
            ),
            slide=(
                "Title at top in bold dark navy sans-serif: 'SAME PERSON, "
                "NEW SITUATION'. Centre: the same four-row horizontal-bar "
                "chart with rows labelled AFFORDABILITY, CONVENIENCE, "
                "QUALITY, STYLE. But now the bar lengths have SHIFTED: "
                "AFFORDABILITY is short, CONVENIENCE is medium, QUALITY is "
                "the longest (soft green), STYLE is medium. Clean 16:9 "
                "landscape. Spell exactly."
            ),
        ),
        SubShot(
            kind="infographic",
            is_beat_start=False,
            narration=(
                "Same person, same framework, new ranking. That's normal. "
                "Revisit the priorities when the situation changes."
            ),
            edit_instruction=(
                "Add a slate-gray caption below the bar chart: 'Revisit "
                "when the situation changes.' Keep EVERYTHING ELSE exactly "
                "as is -- same title, same four row labels, same bar "
                "lengths. Spell exactly."
            ),
            slide="",
        ),
    ],
)
