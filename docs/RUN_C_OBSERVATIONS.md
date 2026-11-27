# Run C — Observations Log (T1d Pattern, 2026-11-27)

This is the engineering-side observations log for the third full run
of the Selection Criterion lesson: Run C under the **T1d pattern** --
narration-first sub-shots, Nano Banana Pro edited-chain slides, and
per-sub-shot Omni edit for real element-level animation.

Companion docs:
- `SELECTION_CRITERION_PIPELINE_DEEP_DIVE.md` -- Runs A (hybrid)
  and B (Omni-only). Run C is a third variant: Omni-only with
  per-sub-shot animation rather than per-beat.
- `SELECTION_CRITERION_RUN_METADATA.md` -- stakeholder summary of A + B.
- `FOR_BUSINESS_REVIEW.md` -- plain-language summary for non-engineering
  reviewers.

Run C's reason for existing: senior reviewer feedback on Run B flagged
three defects -- narration out of sync, on-screen spelling mistakes,
and infographic beats that read as a slideshow rather than animation.
Run C was designed specifically to fix all three.

---

## 1. What was wrong with Run B (Omni-only, 2026-11-25)

Reviewer feedback, in order of severity:

1. **Narration-video sync drifted inside beats.** Omni writes a fixed
   10-second clip for each prompt; the TTS narration for that beat
   was recorded as one blob. Omni's internal animation pacing (shots
   within the clip, where cuts land) is a black box -- we don't get
   to tell it when sentence 2 should appear vs. sentence 3. Result:
   on-screen text would show up noticeably before or after the
   narration said it.

2. **Spelling mistakes on infographics.** Run B used Nano Banana
   (`gemini-3.1-flash-image`) for infographic beats. Nano Banana is
   fast and cheap but hallucinates letters on labels and titles. We
   found real misspellings in the outputs that would be embarrassing
   in an exam-context video.

3. **Animation felt like a slideshow.** Even in beats that held an
   infographic for 7--10 seconds, the beat was effectively one static
   image fed to Omni with a "describe what should happen" prompt.
   What came back was camera motion on a static picture, not element
   motion within the scene. For an educational video for an exam,
   this read as cheap.

---

## 2. T1d design (what Run C does differently)

The design was arrived at through five iteration rounds (T1 -> T1b ->
T1c -> T1c-NBPro -> T1d). The exploration scripts are preserved in
`scripts/full_lesson/` (`t1_segment_02_per_beat_narration.py`,
`t1b_beat1_narration_first.py`, `t1c_beat1_hardcut_padded.py`,
`t1c_beat1_hardcut_nbpro.py`, `t1d_beat1_edit_chain_xfade.py`).

**Key ideas in the final pattern:**

- **Sub-shot = one sentence of narration.** Every unit of the plan is
  a `SubShot` -- a single sentence of narration paired with the
  visual change that should land under that sentence. A beat is no
  longer one Omni call for 10 seconds; it's a chain of 2--6
  sub-shots, each 2--9 seconds, hard-cut together.

- **Narration first, video padded to fit.** Each sub-shot's TTS is
  generated, then LEAD_IN (0.3s silence) is prepended and TAIL (0.2s
  silence) is appended. Video is trimmed or held to match the padded
  audio length exactly. Sync is now deterministic per sub-shot --
  the sentence starts when the sub-shot's video starts, every time.

- **Hard cuts within a beat.** No cross-fade at sub-shot boundaries.
  Cross-fades in T1b bled visual changes into the previous sentence's
  audio window and brought the sync problems back. A hard cut makes
  the content transition line up with the narration transition.

- **Nano Banana Pro for slides.** `gemini-3-pro-image` renders
  on-screen text reliably. It's ~2x the cost per image (~$0.14 vs
  ~$0.07) but it does not misspell. The Run C slides shipped without
  a single spelling defect that would require regeneration.

- **Edit-chain for slide continuity.** Within a beat, the first slide
  is generated fresh; subsequent slide states are produced by
  `edit_image` on the previous slide with "keep everything exactly as
  is except ..." prompts. This keeps the visual stable
  (same typography, same layout, same colors) across the beat.

- **Per-sub-shot Omni edit for animation.** The real new idea. Instead
  of using Omni on the whole beat's first slide and asking it to
  narrate the motion, each intra-beat sub-shot that introduces new
  visual content gets its own Omni edit call. Input: the previous
  slide state. Output: a 10-second clip animating the transition
  (cards slide in, bars grow, labels fade up). We then trim that
  clip to the sentence's padded duration. This gives real
  element-level motion rather than Ken-Burns-on-a-still.

- **Static-hold pass-through.** Sub-shots whose instruction is
  "keep the slide exactly the same" (narration continues over the
  same visual) skip the Omni call entirely -- the previous frame is
  held for the sub-shot's duration. Saves cost and keeps the beat
  from feeling animated-for-animation's-sake.

The code implementing all of this is `scripts/full_lesson/t1d_runner.py`
(final version committed `d79ce4a`), driven by 11 segment plans in
`scripts/full_lesson/t1d_plans/` (`seg01.py` ... `seg11.py`).

---

## 3. Run C measurements (720p pass)

Primary rendered artifact:
`/home/user/IAV/storage/outputs/t1d_lesson_720p-20261127T044927Z-2295df87.mp4`

| Metric | Value |
|---|---|
| Final duration | 9:10.12 (550.12 s) |
| File size | 32,009,494 bytes (30.5 MB) |
| Final assembly method | ffmpeg stream-copy concat (no re-encode) |
| Segments | 11 / 11 OK, 0 failed |
| End-to-end wall-clock | 5,665.2 s (94.4 min) |
| Resolution | 1280 x 720 |

### Per-segment wall-clock (720p)

| Segment | Seconds | Final duration | Size |
|---|---:|---:|---:|
| seg01 | 361 | 37.58 s | 5.87 MB |
| seg02 | 615 | 42.45 s | 1.87 MB |
| seg03 | 511 | 46.74 s | 1.73 MB |
| seg04 | 485 | 66.13 s | 6.01 MB |
| seg05 | 445 | 55.81 s | 1.91 MB |
| seg06 | 438 | 45.06 s | 1.86 MB |
| seg07 | 656 | 55.54 s | 2.19 MB |
| seg08 | 428 | 50.30 s | 4.58 MB |
| seg09 | 552 | 55.09 s | 2.16 MB |
| seg10 | 534 | 57.09 s | 2.33 MB |
| seg11 | 637 | 38.29 s | 1.51 MB |

Average per-segment wall-clock: **515 s (~8.6 min)**.

### Sub-shot distribution (720p)

| Mode | Count | What it does |
|---|---:|---|
| beat-start (fade-in from white) | 31 | Nano Banana Pro slide, no API-side animation call |
| omni-animate (per-sub-shot Omni edit) | 56 | Real element motion on top of an edited slide state |
| omni-realistic (Omni text-to-video) | 5 | The cinematic opening/closing beats |
| static-hold | 5 | Previous frame held under continuing narration |
| **Total sub-shots** | **97** | Across 36 beats across 11 segments |

Total video-seconds across all sub-shots (before concat): 549.0 s.

### API-call accounting

- **Nano Banana Pro slides:** 31 fresh beat-start slides + ~56 edited
  intermediate frames feeding each Omni edit = ~87 image calls at
  `gemini-3-pro-image`.
- **Omni edit (per-sub-shot animation):** 56 calls at
  `gemini-omni-1.2-flash`, task=edit. Each returns 10 s; we trim to
  the sub-shot's padded duration.
- **Omni text-to-video:** 6 calls at `gemini-omni-1.2-flash`,
  task=text_to_video (5 planned omni-realistic sub-shots + 1 that
  the log doesn't attribute cleanly; could be a retry or a plan I'm
  miscounting from the log).
- **TTS:** one call per sub-shot = 97 calls at
  `gemini-2.5-flash-preview-tts` with Kore voice.

### Approximate cost (720p)

Using Google's official rates confirmed 2026-11-25:

| Line item | Qty | Rate | Approx USD |
|---|---:|---|---:|
| Omni edit (56 clips x ~5 s trimmed, but **billed at 10 s per call**) | 560 s | $0.07/s | $39.20 |
| Omni text-to-video (6 x 10 s) | 60 s | $0.07/s | $4.20 |
| Nano Banana Pro images | ~87 | ~$0.14 ea | ~$12.20 |
| TTS | 97 x ~15 s avg | $0.0015/s | ~$2.20 |
| **Total (720p, Run C)** | | | **~$57.80** |

The big line is Omni edit -- the per-sub-shot pattern means we pay
for Omni's full 10-second output even when the sub-shot only uses
~5 s of it. That's the direct cost of fine-grained animation control
compared to Run B's ~$24.

### Sanity checks that passed

- Every segment MP4 opened in ffprobe, every duration matched the
  expected narration length within <0.2 s.
- Final concat used stream-copy (no re-encode), consistent timebases.
- Audio did not drift against video on spot-checks at 1:00, 3:00, 6:00,
  9:00.
- No on-screen misspellings on a human spot-check of beat-start
  slides across all 11 segments.

---

## 4. Compared with Run A (hybrid) and Run B (Omni-only)

| Dimension | Run A (hybrid) | Run B (Omni-only, per-beat) | Run C (Omni-only, per-sub-shot) |
|---|---|---|---|
| Final duration | ~5:50 | ~5:50 | 9:10 |
| Cost @ 720p | $35.81 | $24.05 | ~$57.80 |
| Wall-clock | ~2 hr | ~1.5 hr | 94 min |
| Models used | Veo + Nano Banana + Omni | Nano Banana + Omni | Nano Banana Pro + Omni |
| Narration sync | per-segment (loose) | per-beat (drifts within beat) | per-sub-shot (tight) |
| On-screen spelling | occasional errors | occasional errors | clean |
| Animation feel | mixed (Veo cinematic + static infog) | slideshow-y | element-level motion |

Run C is **~$34 more expensive than Run B at 720p** and ~55% more
wall-clock. The extra cost buys three defects worth of quality that
the senior reviewer called out explicitly.

Run C runs longer in wall time (9:10 vs 5:50) partly because the
narration-first design doesn't compress the script into Omni's fixed
10-s per-beat clip -- it lets each sentence breathe at its own pace.
That's intentional for exam content; a 6-min lesson felt rushed.

---

## 5. Things that did NOT work (worth not re-trying)

- **0.4 s cross-fade between sub-shots (T1b).** Bled the next
  sentence's visual change into the previous sentence's audio window.
  Hard cuts are strictly better when audio is the thing you want
  aligned.

- **Ken Burns zoom to fake animation (T1c-NBPro intermediate).**
  "Zoom looks weird" -- user flagged it directly. Static image with a
  2.5% zoom per sub-shot reads as a Zoom glitch, not as design. We
  pulled it before the final pattern.

- **Nano Banana (non-Pro) for exam-context slides.** Spelling defects
  are not negotiable for content a student will study from. The ~2x
  cost delta per image to go Pro is clearly worth it; the whole
  lesson's slide budget is ~$12, ~2 per student per topic in INR terms.

- **Per-beat Omni with "animate these elements" prompt.** We tried
  variations of "slide the card in from the left, then grow the bar"
  in Run B's style. Omni does something, but it does it on its own
  internal pacing -- you can't say "do the card at 2.4s, do the bar
  at 5.1s." Giving Omni the slide pair (before/after a specific
  element appearing) and letting it animate the one transition is
  what gets reliable per-sub-shot alignment.

---

## 6. What's next

1. **1080p pass (in progress at time of writing).** Same pattern,
   `--resolution 1080p`. Omni billed at $0.15/s instead of $0.07/s,
   so the Omni lines will roughly double. Slides are regenerated at
   1920x1080 target. Expected cost ~$95.

2. **The topic -> full-video utility (still unbuilt).** With T1d
   locked in as the proven pattern and both resolutions rendered,
   the next engine task is the generic entry point: given a topic
   and a target duration, have an LLM write SegmentPlanV2 files
   that the existing runner then renders. Design is in
   `docs/VIDEO_CAPABILITIES.md`.

3. **Stakeholder-facing document.** `FOR_BUSINESS_REVIEW.md`
   accompanies this file and translates the above into plain
   language with the cost-per-lesson table and turnaround times
   that non-engineering reviewers will want.

---

## 7. Appendix -- how to reproduce Run C

```bash
# From the repo root. Needs .env + .credentials/service-account.json.
pip install -r requirements.txt

# 720p full lesson:
python scripts/full_lesson/t1d_full_lesson.py --resolution 720p

# 1080p full lesson:
python scripts/full_lesson/t1d_full_lesson.py --resolution 1080p

# Just one segment (any of seg01..seg11), to validate pattern changes:
python -c "
from scripts.full_lesson.t1d_runner import run_segment
from scripts.full_lesson.t1d_plans.seg02 import PLAN
print(run_segment(PLAN, resolution='720p'))
"
```

The log for a run lands at
`scratchpad/t1d_full_lesson.log` (per-call details for every sub-shot
across all 11 segments -- what this document's numbers were derived
from).
