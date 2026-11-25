"""Segment 3: Define the need and constraints (2:15-3:30). ~40s."""
from iav.capabilities.video_hybrid_segment import SegmentPlan
from scripts.full_lesson._shared import veo, infog

PLAN = SegmentPlan(
    title="Seg 3: Need and constraints",
    beats=[
        infog(10,
              "Title at top in bold dark navy: 'START WITH THE NEED'. Centre: a "
              "large rounded rectangle card in soft navy outline labelled 'THE "
              "NEED' at top, with a short caption inside in slate-gray: 'A "
              "laptop for university coursework.' Simple flat design, clean "
              "white space around.",
              "Animate: the 'NEED' card fades into the centre of the slide and "
              "scales up slightly, as if being presented. The caption text "
              "inside types in character by character, left to right."),
        infog(10,
              "Title at top: 'THEN ADD THE CONSTRAINTS'. The same 'NEED' card "
              "from before is in the centre. Now, three smaller connected cards "
              "fan out below it, each one a rounded rectangle labelled in clean "
              "sans-serif: left card 'BUDGET: under 60,000', middle card "
              "'TIME: needed by next month', right card 'CONTEXT: shared "
              "with sibling'. Lines connect the central NEED card to each "
              "constraint card. Soft navy palette throughout.",
              "Animate: starting with just the NEED card centred, the three "
              "constraint cards appear one by one -- budget first, then time, "
              "then context -- each sliding in from below and connecting to the "
              "NEED card with a line that draws itself."),
        infog(10,
              "Title at top: 'SAME NEED, DIFFERENT PEOPLE'. Two student avatar "
              "icons side by side (simple navy silhouettes, one labelled "
              "'STUDENT A', one labelled 'STUDENT B'). Each has a thought "
              "bubble above containing a laptop icon and a small chip of text: "
              "Student A's chip reads 'light, long battery'. Student B's chip "
              "reads 'powerful, big screen'. Clean minimalist flat design.",
              "Animate: both student silhouettes appear first side by side, "
              "then their thought bubbles fade in above them simultaneously, "
              "then the text chips inside each bubble appear one after the "
              "other."),
    ],
    narration_script=(
        "Good selection starts with a clear need. What are we actually trying "
        "to get? Say we need a laptop for university coursework. That's the "
        "need. "
        "Then come the constraints. What's our budget? When do we need it by? "
        "What's the context -- will we share it with a sibling? These "
        "constraints shape which options are even worth looking at. "
        "And here's why constraints matter: the same need can suit two people "
        "very differently. One student needs something light with long battery "
        "life for a daily commute. Another needs something powerful with a big "
        "screen for design work at home. Same need. Different constraints. "
        "Different right answers."
    ),
)
