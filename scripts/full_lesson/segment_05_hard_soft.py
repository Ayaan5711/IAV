"""Segment 5: Hard and soft criteria (5:15-7:00). ~40s."""
from iav.capabilities.video_hybrid_segment import SegmentPlan
from scripts.full_lesson._shared import infog

PLAN = SegmentPlan(
    title="Seg 5: Hard and soft criteria",
    beats=[
        infog(10,
              "Title at top in bold dark navy: 'HARD CRITERIA'. Below the "
              "title, a large clean 'measuring tape' or ruler illustration in "
              "the centre, with a short slate-gray caption underneath: "
              "'Objectively verifiable -- the number is the number.' On either "
              "side, two example chips labelled 'PRICE' and 'WEIGHT' in clean "
              "sans-serif.",
              "Animate: the measuring tape icon appears in the centre first, "
              "then the caption types in character by character, then 'PRICE' "
              "and 'WEIGHT' chips slide into place from the left and right "
              "sides simultaneously."),
        infog(10,
              "Title at top: 'SOFT CRITERIA'. Centre: a simple illustrated "
              "face icon with a thinking expression (navy outline on white), "
              "caption underneath in slate-gray: 'Judgement call -- depends on "
              "the person.' Two example chips on either side labelled "
              "'COMFORT' and 'STYLE'. Consistent flat design with the previous "
              "slide.",
              "Animate: the thinking-face icon appears centrally first, then "
              "the caption types in, then the two chips 'COMFORT' and 'STYLE' "
              "slide in from the sides and settle."),
        infog(10,
              "Title at top: 'TWO SEPARATE QUESTIONS'. A clean 2x2 grid in the "
              "centre of the slide, labelled axes: vertical axis "
              "'IMPORTANCE' (with arrow pointing up on the left), horizontal "
              "axis with 'OBJECTIVE' on the left and 'SUBJECTIVE' on the "
              "right. Four empty quadrants.",
              "Animate: the axis lines draw themselves in first (vertical "
              "line, then horizontal line), then the axis labels appear "
              "('IMPORTANCE' at top left, 'OBJECTIVE' at bottom left, "
              "'SUBJECTIVE' at bottom right). The grid is now fully drawn and "
              "ready."),
        infog(10,
              "Title: 'TWO SEPARATE QUESTIONS'. Same 2x2 grid as the previous "
              "slide (vertical axis 'IMPORTANCE', horizontal axis "
              "'OBJECTIVE'/'SUBJECTIVE'). Now four labelled chips populate "
              "the grid: 'PRICE' in the upper-left quadrant (important + "
              "objective, in soft green), 'FUEL EFFICIENCY' in the lower-left "
              "(less important + objective, in soft gray), 'COMFORT' in the "
              "upper-right (important + subjective, in soft green), 'COLOR' in "
              "the lower-right (less important + subjective, in soft gray).",
              "Animate: starting with just the empty grid visible, the four "
              "chips appear one by one in their respective quadrants in "
              "sequence: PRICE (upper-left) first, then FUEL EFFICIENCY "
              "(lower-left), then COMFORT (upper-right), then COLOR "
              "(lower-right). Each chip slides into position."),
    ],
    narration_script=(
        "Not every criterion is measured the same way. Some are hard criteria "
        "-- things we can verify objectively. Price is a number. Weight is a "
        "number. Either the laptop fits in your bag or it doesn't. "
        "Others are soft criteria. Comfort. Style. The right feel. These are "
        "judgement calls -- what works for one person might not work for "
        "another. "
        "Here's the subtlety worth remembering: hard versus soft is one "
        "question. Important versus less important is a completely separate "
        "question. A measurable feature like fuel efficiency might be only "
        "mildly important, while a judgement call like comfort might be the "
        "deciding factor. Keep the two questions apart."
    ),
)
