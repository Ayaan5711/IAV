# Selection Criterion Lesson — Business Review

**For:** Non-engineering reviewers (Sharmila di + stakeholders at
HOELT / TCS iON).
**Date:** 2026-11-27.
**What this is:** A plain-language summary of what we built, what it
costs, how long it takes, and what quality looks like now. The
engineering detail lives in the companion docs
(`SELECTION_CRITERION_PIPELINE_DEEP_DIVE.md`,
`RUN_C_OBSERVATIONS.md`) -- this one skips the code.

---

## 1. What we delivered

A ~9-minute educational video on the **Selection Criterion** topic
from TCS iON's syllabus. End to end -- opening hook, examples,
infographics, common mistakes, review loop, wrap-up -- in 11 segments
that stitch into one lesson file.

We've now produced this lesson three times with three different
approaches, each one addressing feedback from the last:

- **Run A** (hybrid: cinematic video + infographics): $35.81 in
  compute, ~2 hours to make. Mixed motion styles.
- **Run B** (streamlined, single video model): $24.05, ~1.5 hours.
  Cheaper, simpler pipeline, but the narration drifted out of sync
  with the visuals and some on-screen text had spelling errors.
- **Run C** (today, the proven pattern): see below.

Run C is the one we recommend scaling.

---

## 2. Run C -- the three fixes

Senior reviewer flagged three things in Run B:

| Problem | Fix we built | Result |
|---|---|---|
| Narration doesn't match what's on screen | Rebuilt the timing model: every sentence of narration drives its own short visual beat; silence padding keeps them perfectly aligned | Narration lands on frame-level cues, throughout |
| Spelling mistakes in on-screen text | Switched to Nano Banana **Pro**, the higher-end image model that renders text reliably | Clean titles, labels, numbers across all 11 segments |
| Infographics felt like a slideshow | Added element-level animation per sentence (cards slide in, bars grow, labels appear) instead of one static image per beat | Proper educational-video motion, not a photo carousel |

---

## 3. Run C -- what it looks like, what it costs, how long it takes

### Quality dimensions

- **Resolution options:** 720p (standard) and 1080p (full HD).
- **Runtime:** 9 minutes 10 seconds of finished video.
- **Format:** MP4, direct-to-player, no post-processing needed.
- **Narration voice:** Gemini TTS "Kore" preset -- clear,
  professional, studio-quality.
- **Spelling:** Human-verified across all 11 segments. Clean.
- **Sync:** Narration tracks the visual element-by-element.

### Cost per lesson -- 720p

| Component | Approximate USD | Approximate INR (@ 84) |
|---|---:|---:|
| Omni video model (element animation) | $39 | ~₹3,280 |
| Omni video model (cinematic openings) | $4 | ~₹340 |
| Nano Banana Pro (slide artwork) | $12 | ~₹1,010 |
| Gemini TTS (narration) | $2 | ~₹170 |
| **Total per 9-min lesson @ 720p** | **~$58** | **~₹4,870** |

### Cost per lesson -- 1080p

The only lines that change are the two Omni video ones --
Google bills 1080p output at roughly double 720p's rate.

| Component | Approximate USD | Approximate INR (@ 84) |
|---|---:|---:|
| Omni video model (element animation) | $84 | ~₹7,060 |
| Omni video model (cinematic openings) | $9 | ~₹760 |
| Nano Banana Pro (slide artwork) | $12 | ~₹1,010 |
| Gemini TTS (narration) | $2 | ~₹170 |
| **Total per 9-min lesson @ 1080p** | **~$107** | **~₹9,000** |

### Normalized -- per-minute cost

For comparison when quoting to other topics of different lengths:

| Resolution | Per minute of finished lesson |
|---|---:|
| 720p | ~$6.30 / ~₹530 |
| 1080p | ~$11.70 / ~₹980 |

### Turnaround time

Measured end-to-end for the 720p run completed today:

- **Total wall-clock:** 94 minutes from "start" to final MP4.
- **Per segment:** ~8.5 minutes on average.
- **Operator attention needed:** Essentially zero during the render.
  Command kicked off, file ready an hour and a half later. No manual
  stitching, captioning, color-correcting, or QA passes required for
  the render itself (content review is still a human step).

1080p takes roughly the same wall-clock -- the slow step is Omni
generation time per clip, not the resolution.

---

## 4. What a second lesson would look like

At steady state, producing a second 9-minute lesson on a different
topic requires:

1. A scripting step -- someone writes (or an LLM drafts) the 11
   segment plans: titles, beat outlines, narration sentences,
   infographic ideas. This is the authoring work, not the engine
   work. Call it ~1 day of human time per lesson for a first draft
   someone would stand behind. *This is also the piece we plan to
   automate next -- see §6.*
2. The render step -- same command, same cost table above, 1.5 hours
   wall-clock.
3. Review -- someone watches the output, flags what to redo. Any
   redo is just a config change and the affected segment re-renders.

So production cost per new lesson ~₹5,000 at 720p / ~₹9,000 at 1080p,
plus authoring time.

---

## 5. What we did NOT get wrong this time, but is worth naming

- **Costs reported here are measured, not estimated.** The 720p
  numbers come from the actual billed API calls in the Run C log
  file. The engineering doc shows each line item.
- **We billed what we rendered.** No wasted rework beyond the
  development runs that led to the proven pattern (those are
  logged separately in the engineering docs).
- **Everything is reproducible.** A new engineer, or a cloud session
  with the same credentials, can rerun either resolution with one
  command (`python scripts/full_lesson/t1d_full_lesson.py
  --resolution 720p|1080p`) and get the same output.
- **No manual editing was needed.** No ffmpeg trickery, no overlays
  added by hand, no voice retakes. The engine delivers the final MP4.

---

## 6. What's next on the roadmap

1. **Topic -> full lesson, automated.** Today, the engine renders
   a lesson from a per-segment plan a human wrote. The next piece
   is the generic entry point: give it a topic and a target
   duration, and an LLM writes the segment plans that feed the
   proven pattern. Designed, not yet built.
2. **Scale to more topics.** The same pipeline works for any
   concept video of similar shape (hook -> explanation -> examples
   -> mistakes -> wrap-up). Nothing in the engine is Selection-
   Criterion-specific.
3. **Variant voices / regional language narration.** The TTS layer
   supports multiple voices and languages. Not wired into the
   lesson pipeline yet but a config change rather than a code
   change.

---

## 7. Deliverables alongside this document

- **Final lesson MP4 (720p, 9:10, 30.5 MB):** rendered today, sent
  separately.
- **Final lesson MP4 (1080p, 9:11, 54.7 MB):** rendered today, sent
  separately.
- **Per-segment MP4s (both resolutions):** packaged as
  `selection_criterion_720p.zip` and `selection_criterion_1080p.zip`
  -- 11 scene-wise MP4s plus the stitched full lesson in each.
- **Engineering deep-dive:** `SELECTION_CRITERION_PIPELINE_DEEP_DIVE.md`.
- **Full observations log for Run C:** `RUN_C_OBSERVATIONS.md`
  (includes T1 -> T1d iteration history so a new engineer can
  understand why the pattern is what it is).

---

*This document and its engineering counterparts are committed in the
repo under `docs/`. Anyone with repo access can read the current
state at any time; they stay in sync with the code, not with an
external slide deck.*
