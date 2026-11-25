"""Segment 9: Common decision mistakes (11:30-12:45). ~40s."""
from iav.capabilities.video_hybrid_segment import SegmentPlan
from scripts.full_lesson._shared import infog

PLAN = SegmentPlan(
    title="Seg 9: Common decision mistakes",
    beats=[
        infog(10,
              "Title at top in bold dark navy: 'FIVE COMMON MISTAKES'. Below "
              "the title, a scattered cluster of five small 'distraction' "
              "icons spread across the slide: a shiny-sparkle icon, a "
              "crowd-of-people silhouette, a wallet icon, a question-mark "
              "icon, and a rewound-time icon. All icons in soft gray at low "
              "contrast, visually noisy. Caption near the bottom in slate-"
              "gray: 'These pull decisions off course.'",
              "Animate: the five distraction icons appear one by one in "
              "random-feeling positions across the slide, each wiggling "
              "briefly as it lands. The caption types in last. Result: a "
              "visually messy, distracted-looking slide."),
        infog(10,
              "Title: 'FIVE COMMON MISTAKES'. The slide now has a clean "
              "numbered checklist in the centre (replacing the previous "
              "distractions). Five rows top to bottom, each row a navy "
              "sans-serif line prefixed by a small navy circle numeral: '1. "
              "Choosing by appearance alone', '2. Following what others "
              "picked', '3. Ignoring ongoing costs', '4. Using incomplete "
              "information', '5. Changing criteria to justify a favourite'.",
              "Animate: starting from the cluttered previous slide, all the "
              "distraction icons fade out and sweep away. Then the five "
              "numbered mistakes appear one line at a time, in order 1 "
              "through 5, with a short pause between each."),
        infog(10,
              "Title: 'THE ANTIDOTE'. Centre: two rounded rectangular cards "
              "side by side. Left card has a large navy checkmark icon at "
              "top and the label 'EVIDENCE' underneath in bold sans-serif. "
              "Right card has a scale/gavel icon and the label 'CRITERIA "
              "SET IN ADVANCE'. A short slate-gray caption spans below both "
              "cards: 'Decide the rules before you decide the winner.'",
              "Animate: the two cards fade in from the left and right "
              "respectively and settle in the centre. The icons inside each "
              "card appear first, then the labels beneath them, then the "
              "caption types in across the bottom."),
    ],
    narration_script=(
        "Five mistakes come up again and again. Choosing by appearance "
        "alone -- picking the option that looks shiniest, not the one that "
        "actually fits. Following what other people picked, when their "
        "situation isn't your situation. Ignoring ongoing costs, the fuel "
        "and maintenance after the price tag. Using incomplete information, "
        "when a little more research would change the answer. And the "
        "trickiest -- changing the criteria at the last moment to justify "
        "an option you already fell in love with. "
        "The antidote is simple to state, harder to practice. Decide the "
        "rules before you decide the winner. Agree on what matters -- the "
        "evidence you'll use, the criteria you'll weigh -- before you even "
        "look at the options."
    ),
)
