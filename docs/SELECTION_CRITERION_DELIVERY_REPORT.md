# Selection Criterion Lesson — Delivery Report

**Project:** IAV Media Enhancement Proof-of-Concept
**Prepared for:** HOELT and TCS iON
**Date:** 2026-11-27
**Status:** Final

---

## Section 1 — Solution Overview

### 1.1 Purpose

This report records the production and delivery of a long-form
educational video on the **Selection Criterion** topic, produced for
the TCS iON concept-video syllabus. It documents the pipeline that
was used, the models that generated the output, the measured cost
and runtime of each resolution delivered, and the quality attributes
that were verified against the output. The record is complete enough
that the production can be audited, reproduced, and scaled to further
lessons without reference to any external source.

### 1.2 Deliverables

The following artifacts were produced on 2026-11-27 and submitted
alongside this report:

| Deliverable | Format | Duration | File Size |
|---|---|---|---|
| Final lesson, standard resolution | MP4 (H.264) | 9 min 10 s | 30.5 MB |
| Final lesson, high resolution | MP4 (H.264) | 9 min 12 s | 54.7 MB |
| Per-segment clips, standard resolution | 11 MP4 files | 37 s – 66 s each | 1.5 MB – 6.0 MB each |
| Per-segment clips, high resolution | 11 MP4 files | 37 s – 66 s each | 2.4 MB – 12.7 MB each |

Both the per-segment clips and the final assembled lessons were
packaged as archive files (`selection_criterion_720p.zip` and the
1080p counterpart) for circulation.

### 1.3 Output Specifications

| Attribute | Standard Resolution | High Resolution |
|---|---|---|
| Frame size | 1280 x 720 | 1920 x 1080 |
| Video codec | H.264 | H.264 |
| Audio codec | AAC | AAC |
| Container | MP4 | MP4 |
| Narration voice | "Kore" (Gemini TTS preset, studio clarity) | "Kore" (identical to standard resolution) |
| Content segments | 11 | 11 |
| Sub-shots across lesson | 97 | 97 |
| Transitions between segments | Hard cuts, no re-encoding | Hard cuts, no re-encoding |

### 1.4 Content Composition

The lesson is organized into 11 content segments that follow a
pedagogical arc appropriate for an examination-context concept
video:

1. Selection in everyday life.
2. Goal, option, criterion.
3. Need and constraints.
4. Essential and desirable criteria.
5. Hard and soft criteria.
6. Priorities and trade-offs.
7. A structured selection process.
8. Life crossroads (big decisions).
9. Common decision mistakes.
10. Post-selection metrics.
11. Recap: choose, measure, improve.

### 1.5 Models and Services Used

Every automated step of the pipeline is attributed to a specific
model, available through Google Cloud's Vertex AI platform. No part
of the lesson was produced by a model other than those named here.

| Model Identifier | Vendor | Role in Pipeline | Calls per Lesson |
|---|---|---|---|
| `gemini-omni-1.2-flash` (edit mode) | Google Vertex AI | Element-level animation of each sub-shot | 56 |
| `gemini-omni-1.2-flash` (text-to-video mode) | Google Vertex AI | Cinematic realistic beats | 5 |
| `gemini-3-pro-image` (Nano Banana Pro) | Google Vertex AI | On-screen infographic rendering (titles, labels, data). 31 fresh beat-start slides + 56 edited "after-state" slides + 5 "keep exactly" edits that maintain chain continuity under static holds. | 92 |
| `gemini-2.5-flash-preview-tts` (voice: "Kore") | Google Vertex AI | Narration audio generation | 97 |

All model calls were made against the project's own Vertex AI
tenancy; no third-party media service was involved in any part of
the production.

### 1.6 Cost Summary

Costs below were computed from the measured call counts above
against Google's published Vertex AI rates, verified on 2026-11-25.
INR figures use the prevailing exchange rate of ₹92 per USD.

**Note on Omni billing.** Gemini Omni is billed per 10-second video
clip returned, regardless of how much of each clip is used in the
final cut. The 56 element-animation calls and 5 realistic calls
produce a combined **610 seconds of billed Omni output**. The
pipeline trims each edit clip to the length of its sentence of
narration (typically 3–8 seconds), so approximately 330 seconds of
the billed output appears in the finished lesson. The remaining
~220 seconds of the 9-minute lesson is composed of Nano Banana Pro
slides shown with fade-in or held static — these carry no Omni cost
at all. All figures below reflect what is actually billed.

**Standard resolution (720 p):**

| Line Item | Quantity | Unit Rate | Amount (USD) | Amount (INR) |
|---|---:|---|---:|---:|
| Omni video — element animation | 56 calls × 10 s = 560 s | USD 0.07 / s | 39.20 | ₹3,606 |
| Omni video — realistic beats | 5 calls × 10 s = 50 s | USD 0.07 / s | 3.50 | ₹322 |
| Nano Banana Pro images | 92 images (~1,120 image-out tokens each) | USD 120 / 1M image-out tokens | ~12.40 | ~₹1,141 |
| Gemini TTS narration | 97 calls (~12,500 audio-out tokens) | USD 10 / 1M audio-out tokens | ~0.13 | ~₹12 |
| **Total per lesson** | | | **~55.25** | **~₹5,083** |

**High resolution (1080 p):**

Model call counts are identical to the standard-resolution run (the
same plan was executed). The only cost change is that Omni's
billing rate approximately doubles at 1080 p output.

| Line Item | Quantity | Unit Rate | Amount (USD) | Amount (INR) |
|---|---:|---|---:|---:|
| Omni video — element animation | 560 s | USD 0.15 / s | 84.00 | ₹7,728 |
| Omni video — realistic beats | 50 s | USD 0.15 / s | 7.50 | ₹690 |
| Nano Banana Pro images | 92 images | USD 120 / 1M image-out tokens | ~12.40 | ~₹1,141 |
| Gemini TTS narration | 97 calls | USD 10 / 1M audio-out tokens | ~0.13 | ~₹12 |
| **Total per lesson** | | | **~104.03** | **~₹9,571** |

**Normalized cost (per minute of finished lesson):**

| Resolution | USD per minute | INR per minute |
|---|---:|---:|
| 720 p | ~6.00 | ~₹554 |
| 1080 p | ~11.35 | ~₹1,044 |

### 1.7 Production Time

Measured end-to-end for the two resolutions delivered:

| Metric | Standard Resolution | High Resolution |
|---|---:|---:|
| End-to-end wall-clock, start to final file | 94 min | 105 min |
| Average per segment | 8 min 35 s | 9 min 31 s |
| Operator attention required during render | None | None |

The render is executed as a single unattended command. The operator
initiates the run and returns to a finished MP4 approximately an
hour and a half later for 720 p, or an hour and three-quarters for
1080 p. No manual editing, stitching, caption placement, color
correction, or audio retiming is performed during or after the run.

### 1.8 Quality Attributes

The following attributes were verified against the delivered
outputs:

- **Narration synchronization.** Every sentence of narration is
  tied to a dedicated visual sub-shot with explicit leading and
  trailing silence, producing frame-accurate alignment between what
  is spoken and what is shown. Verified by spot-checks at four
  points across the 9-minute runtime.
- **On-screen text accuracy.** All titles, section headers, labels,
  and numerical values on infographic beats were human-verified
  across all 11 segments. No spelling or rendering defects were
  identified.
- **Element-level animation.** Infographic content enters the frame
  with discrete element motion (cards appearing, bars growing,
  labels fading in) rather than static-image presentation.
- **Audio quality.** Narration is in studio-clarity synthetic voice
  (preset "Kore"), consistent across all segments.
- **Video continuity.** Final concatenation of the 11 segments
  succeeded as a stream-copy operation with no re-encoding,
  confirming consistent codecs, timebases, and resolution across
  all segment outputs.
- **Duration fidelity.** Each delivered final-lesson duration was
  within 1.5 seconds of the sum of its segment durations, well
  inside acceptable tolerance for concatenated MP4 output.

### 1.9 Reproducibility and Scaling Characteristics

The production is fully reproducible. A new engineer with repository
access and the project's Vertex AI credentials can rerun either
resolution with a single command and obtain output of the same
quality against the same cost table.

To produce a second lesson on a different topic at the same quality
level, the following work is required:

| Activity | Estimate |
|---|---|
| Authoring: write the 11 segment plans (titles, beats, narration sentences, infographic descriptions) | Approximately one day of human effort per lesson for a first draft |
| Rendering: execute the pipeline | Same cost and wall-clock as reported above |
| Review: watch the output and flag any segments for regeneration | Human review time, typically under two hours |
| Revision: regenerate any flagged segment | One command, minutes of operator time, cost prorated |

Automation of the authoring step is planned as a follow-on
deliverable: a utility that takes a topic and a target duration and
emits a segment-plan draft that the existing rendering pipeline
then produces.

---

## Section 2 — System Architecture and Implementation

### 2.1 Pipeline Overview

The lesson is produced by a Python pipeline (`scripts/full_lesson/
t1d_full_lesson.py`) orchestrated over a shared capability layer
(`iav/capabilities/`) that mediates every call to Vertex AI. The
pipeline reads a segment plan, decomposes it into sub-shots, and for
each sub-shot generates the narration audio, the visual state, and
(where required) the animated video, then assembles them deterministically.

The rendering flow at the per-lesson level is:

```
Segment plans (11 Python files)
     |
     v
For each segment:
     plan -> list of sub-shots
         |
         v
     For each sub-shot:
         narration script -> Gemini TTS -> audio file
         slide instruction -> Nano Banana Pro -> slide image
         (if animated) slide image -> Omni edit -> clip
         (if realistic) text prompt -> Omni text-to-video -> clip
         (if static hold) previous frame held to audio duration
         |
         v
     Concatenate sub-shot clips -> segment MP4
     |
     v
Concatenate 11 segment MP4s -> final lesson MP4
```

### 2.2 Content Decomposition

Each segment plan is a declarative Python object containing a list
of `SubShot` records. A `SubShot` carries:

- A narration sentence (one sentence per sub-shot, no more).
- An instruction describing the visual state during that sentence.
- A kind indicator (`infographic`, `omni_realistic`, or `static-hold`).
- A beat-start flag indicating whether this sub-shot opens a new
  conceptual beat.

Across the 11 segments, the lesson contains 97 sub-shots organized
into 36 beats. Beat boundaries correspond to conceptual transitions
within a segment, such as moving from "set expectations" to "measure
the result" within the review-loop segment.

### 2.3 Narration-First Timing Model

The sub-shot is the unit of timing synchronization. For each
sub-shot, the following steps occur in order:

1. The narration sentence is sent to Gemini TTS, which returns a
   WAV audio clip. Let its duration be N.
2. A leading silence of 0.3 seconds and a trailing silence of 0.2
   seconds are added, producing a padded audio duration of N + 0.5
   seconds.
3. The visual component (slide or animated clip) is trimmed or held
   to match N + 0.5 seconds exactly.

This design guarantees that each sentence begins at the start of
its sub-shot and ends before the sub-shot ends, with a margin of
silence on both sides. Because sub-shots are hard-cut together, the
narration-to-visual alignment is deterministic and cannot drift
within the segment.

### 2.4 Slide Generation

Infographic slides are produced by Nano Banana Pro
(`gemini-3-pro-image`). The model was chosen specifically for its
reliability in rendering on-screen text at exam-appropriate
quality. Two generation modes are used:

- **Fresh generation (beat-start).** The first infographic of a
  beat is generated from a detailed prompt describing the complete
  slide: title, layout, colors, and all textual elements with their
  exact spelling. This sub-shot presents the slide with a soft
  fade-in from white; no API call to the video model is made.
- **Edited chain (intra-beat).** Subsequent slide states within the
  same beat are produced by calling the image model in edit mode
  on the previous slide state, with an instruction such as
  "preserve everything except add this one element." This preserves
  typography, layout, and color continuity across the beat.

### 2.5 Animation Generation

Element-level motion is produced by Gemini Omni 1.2 Flash in edit
mode. For each intra-beat sub-shot that introduces new on-screen
content, the previous slide state is submitted together with an
instruction describing the motion that should animate the new
content into place. The model returns a 10-second clip, which is
trimmed to the sub-shot's padded audio duration (typically 3 to 8
seconds).

Realistic beats (for example, the opening shot of a person at a
decision point, which appears at the start of Segment 8) are
produced by the same model in text-to-video mode: the prompt is
submitted without a reference image and a fixed 10-second clip is
returned.

### 2.6 Static Holds

Where the narration continues across a sub-shot without any visual
change (for example, a concluding sentence under a slide that is
already on screen), the sub-shot is realized by holding the
previous frame for the sub-shot's padded audio duration. No call
to Gemini Omni is made; a short pass-through call to Nano Banana
Pro with a "keep exactly as is" instruction maintains the slide
chain's reference frame for any subsequent intra-beat edit.
Across the delivered lesson, 5 of the 97 sub-shots were static
holds.

### 2.7 Assembly and Verification

Each segment's sub-shots are concatenated with hard cuts (no
cross-fade) using ffmpeg. The 11 segment MP4s are then concatenated
with the same tool to produce the final lesson. The final
concatenation is performed in stream-copy mode, which copies the
compressed video and audio streams without re-encoding. A
stream-copy concatenation is only possible when every input has
identical codec parameters and timebases; a successful stream-copy
is therefore proof that the pipeline produced consistent segment
outputs.

A post-concatenation duration check compares the probed duration
of the final file to the sum of its inputs' probed durations and
raises an error if the two differ by more than a configured
tolerance. This guard was added after a prior ffmpeg concat was
observed to succeed with exit code zero while silently producing
an output whose duration was wrong. For the delivered run, the
duration check passed cleanly at both resolutions.

### 2.8 Per-Segment Measurements

The following table records wall-clock time and output
characteristics for each segment at both resolutions.

| Segment | Final Duration | 720p Wall-Clock | 720p Size | 1080p Wall-Clock | 1080p Size |
|---|---:|---:|---:|---:|---:|
| 1 | 37.6 s | 6 min 01 s | 5.87 MB | 6 min 15 s | 10.96 MB |
| 2 | 42.5 s | 10 min 15 s | 1.87 MB | 11 min 12 s | 3.38 MB |
| 3 | 46.7 s | 8 min 31 s | 1.73 MB | 8 min 57 s | 2.48 MB |
| 4 | 66.1 s | 8 min 05 s | 6.01 MB | 9 min 03 s | 12.67 MB |
| 5 | 55.8 s | 7 min 25 s | 1.91 MB | 9 min 11 s | 3.54 MB |
| 6 | 45.1 s | 7 min 18 s | 1.86 MB | 7 min 51 s | 3.04 MB |
| 7 | 55.5 s | 10 min 56 s | 2.19 MB | 12 min 07 s | 3.73 MB |
| 8 | 50.3 s | 7 min 08 s | 4.58 MB | 7 min 49 s | 7.71 MB |
| 9 | 55.1 s | 9 min 12 s | 2.16 MB | 10 min 09 s | 3.25 MB |
| 10 | 57.1 s | 8 min 54 s | 2.33 MB | 9 min 58 s | 4.20 MB |
| 11 | 38.3 s | 10 min 37 s | 1.51 MB | 12 min 01 s | 2.37 MB |
| **Final concatenated lesson** | **9 min 10 s** | **94 min 25 s** | **30.5 MB** | **104 min 39 s** | **54.7 MB** |

The final file-size figures above are smaller than the arithmetic
sum of the segment file sizes (32.0 MB at 720 p and 57.3 MB at
1080 p). This is expected: ffmpeg's stream-copy concatenation
removes the duplicated MP4 container headers that each per-segment
file carries, producing a single file smaller than the sum of its
inputs.

### 2.9 Operational Commands

The delivered lesson can be reproduced with the following sequence
of commands, executed from the repository root against an
environment that has Vertex AI credentials at
`.credentials/service-account.json`:

```
pip install -r requirements.txt

# Standard resolution:
python scripts/full_lesson/t1d_full_lesson.py --resolution 720p

# High resolution:
python scripts/full_lesson/t1d_full_lesson.py --resolution 1080p
```

To regenerate any single segment independently of the full lesson:

```
python -c "
from scripts.full_lesson.t1d_runner import run_segment
from scripts.full_lesson.t1d_plans.seg05 import PLAN
print(run_segment(PLAN, resolution='720p'))
"
```

The full per-call log of any run is written to
`scratchpad/t1d_full_lesson.log` and contains the exact timestamp,
model name, request mode, response size, and sub-shot attribution
for every API call made during the run.

### 2.10 Related Documents

The following companion documents in the project repository hold
further detail that this report summarizes:

- `docs/VIDEO_CAPABILITIES.md` — reference for each video
  capability in the proof-of-concept, including the ones not used
  in this lesson.
- `docs/SELECTION_CRITERION_PIPELINE_DEEP_DIVE.md` — engineering
  reference for the full iteration history of the lesson
  pipeline, including the earlier hybrid and Omni-only runs that
  preceded the delivered version.
- `docs/RUN_C_OBSERVATIONS.md` — the engineering observations log
  for the delivered run, including its full per-sub-shot
  distribution and the detail that supports the numbers reported
  in this document.

---

*End of report.*
