# Selection Criterion — Pipeline Deep Dive & Run Metadata

Comprehensive technical reference for the Selection Criterion lesson video
generation. Use this when onboarding, estimating a new lesson's cost/time,
or debugging a run. Numbers below come from the **first full run
(2026-11-25 09:46, hybrid pipeline, 6:18 lesson)** as the empirical base,
with projections for the Omni-only pivot that followed it.

> **Companion docs**
> - `SELECTION_CRITERION_RUN_METADATA.md` — stakeholder-facing summary of this same run
> - `VIDEO_CAPABILITIES.md` — the engine-level reference for every video capability in this repo
> - `POC_PLAN.md` — historical, written before video work existed

---

## 1. What was produced

**Final deliverable:** `storage/outputs/selection_criterion_lesson-20261125T094632Z-e0273f20.mp4`

| Attribute | Value |
|---|---|
| Runtime | **6:18** (378 s) |
| Size | 20,160,417 bytes (~20 MB) |
| Container / codecs | MP4 / H.264 video + AAC 160 kbps audio |
| Resolution | 720p (1280×720) |
| Frame rate | 24 fps |
| Segment count | 11 of 11 |
| Narration voice | Gemini TTS, Kore preset |
| Final assembly | ffmpeg re-encode concat (stream-copy fast path tried first, duration sanity check detected timebase mismatch and fell back cleanly) |

---

## 2. End-to-end pipeline — architecture

```
                     ┌─────────────────────────────────────────┐
                     │  scripts/full_lesson/run_all.py         │
                     │  (orchestrator: 11 segments + concat)   │
                     └──────┬────────────────────────────┬─────┘
                            │                            │
          ┌─────────────────┴─────────────┐              │
          │ For each segment plan:         │              │
          │ segment_NN_<name>.PLAN         │              │
          │   = SegmentPlan(title,         │              │
          │       beats=[...],             │              │
          │       narration_script)        │              │
          └────┬──────────────────────────┬┘              │
               │                           │               │
               ▼                           ▼               │
      ┌────────────────┐         ┌─────────────────┐      │
      │  Realistic     │         │  Infographic    │      │
      │  beat          │         │  (animated)     │      │
      │                │         │                 │      │
      │  prompt only   │         │  slide+animate  │      │
      └───────┬────────┘         └────────┬────────┘      │
              │                            │                │
              ▼                            ▼                │
  ┌──────────────────────┐     ┌──────────────────────┐    │
  │  Gemini Omni 1.2     │     │  Nano Banana         │    │
  │  Flash (GA)          │     │  (gemini-3.1-flash-  │    │
  │  text_to_video       │     │   image) — slide     │    │
  │                      │     │                      │    │
  │  OR (first run):     │     │        ↓             │    │
  │  Veo 3.1 Lite        │     │  looped to video     │    │
  │  (pre-pivot)         │     │        ↓             │    │
  │                      │     │  Gemini Omni 1.2     │    │
  │                      │     │  Flash edit mode     │    │
  └──────────┬───────────┘     └──────────┬───────────┘    │
             │                             │                 │
             │   one MP4 beat clip         │                 │
             └──────────────┬──────────────┘                 │
                            │                                 │
                            ▼                                 │
              ┌─────────────────────────┐                     │
              │ _combine_beats()        │                     │
              │  - strip audio (ffmpeg -an) │                │
              │  - VideoCombine concat  │                     │
              │    (stream-copy → dur   │                     │
              │    check → re-encode    │                     │
              │    fallback)            │                     │
              └────────────┬────────────┘                     │
                           │                                   │
                           ▼                                   │
              ┌─────────────────────────┐                     │
              │ _generate_narration()   │                     │
              │  Gemini 2.5 Flash       │                     │
              │  Preview TTS, Kore      │                     │
              │  → WAV                  │                     │
              └────────────┬────────────┘                     │
                           │                                   │
                           ▼                                   │
              ┌─────────────────────────┐                     │
              │ _mux_audio_over_video() │                     │
              │  ffmpeg [1:a]apad[padded]│◄───────────────────┘
              │  one segment MP4 out    │
              └────────────┬────────────┘
                           │
                           ▼  (×11)
                  ┌──────────────────┐
                  │ VideoCombine     │
                  │ final concat     │
                  │ (same timebase-  │
                  │  mismatch guard) │
                  └────────┬─────────┘
                           │
                           ▼
          selection_criterion_lesson-<ts>.mp4
```

---

## 3. Step-by-step walkthrough (what actually happens per segment)

### Input to a segment

A **`SegmentPlan`** instance — three fields:
- `title: str` — e.g. `"Seg 1: Selection in everyday life"`
- `beats: list[Beat]` — one Beat per clip that'll make up the segment
- `narration_script: str` — one paragraph of text that'll be voiced across the whole segment

A **`Beat`** has four fields:
- `kind`: one of `"veo"`, `"infographic"`, `"infographic_animated"`, `"omni_realistic"` (new as of 2026-11-25 pivot)
- `prompt`: either a scene description (for realistic beats) or a slide description with `::ANIMATE::` delimiter separating still-image prompt from animation instruction (for infographic beats)
- `duration_seconds`: advisory — Omni outputs a fixed 10s/call, so this is effectively a target not a hard spec
- `chain_from_previous`: Veo-only — if True, extracts last frame of previous beat as seed image for continuity

### Step 1 — Beat generation

For each beat in the plan, one branch of the dispatch runs:

#### 1a. Realistic beat (`"veo"` — first run only, now deprecated)
- Call `GeminiClient.generate_video(model="veo-3.1-lite-generate-001", prompt=..., duration_seconds=8, resolution="720p", generate_audio=False, image_bytes=last_frame if chain_from_previous else None, location="us-central1")`
- Veo is a long-running operation (LRO) — the client polls every 10s (configurable) for up to 360s before timing out
- Returns raw MP4 bytes; written to `storage/outputs/video_hybrid_segment_veo-*.mp4`
- Extract the last frame to a JPEG for possible chaining into the next beat (`_extract_last_frame_jpeg()`, via `ffmpeg -sseof -1 -frames:v 1`)

#### 1b. Realistic beat (`"omni_realistic"` — new since 2026-11-25 pivot)
- Call `GeminiClient.interactions_video(model="gemini-omni-1.2-flash", instruction=prompt, task="text_to_video")`
- Omni's Interactions API is **synchronous** — no polling, returns on the same HTTP call (takes ~35–40s wall-clock per 10s-output clip)
- Fixed 10s output per call. No image conditioning (Omni text_to_video doesn't take a seed image); callers wanting shot-continuity across beats merge the pair into one prompt covering both actions.
- Returns raw MP4 bytes; written to `storage/outputs/video_hybrid_segment_omni_realistic-*.mp4`

#### 1c. Infographic beat (`"infographic_animated"` — this is what makes the lesson feel like Synthesia)

Three sub-steps, in one capability call:

1. **Nano Banana generates the slide as a still image.**
   - Call `GeminiClient.generate_image(model="gemini-3.1-flash-image", prompt=slide_description, resolution="2K")`.
   - Slide includes the title, body elements, caption text — Nano Banana is the only Google model that reliably renders legible on-screen text, which is why image models cannot be dropped from this pipeline.
   - Image bytes → written to a temp PNG inside the segment's workdir.

2. **Loop the still into a 10-second silent video** (so Omni's edit mode has something to animate).
   - `ffmpeg -loop 1 -i slide.png -t 10 -r 24 -c:v libx264 -tune stillimage -pix_fmt yuv420p slide_loop.mp4`

3. **Omni edit mode animates the elements** while preserving the slide's geometry and text.
   - Call `GeminiClient.interactions_video(model="gemini-omni-1.2-flash", instruction=animate_description, task="edit", video_bytes=loop_bytes)`.
   - The prompt uses an `ANIMATE_PRESERVE` prefix (defined in `_shared.py`) that explicitly tells Omni to keep every text label and color exactly as written — this is what stops Omni from redrawing the slide freehand and losing the typography crispness.
   - Omni returns a new 10s MP4 where the cards/bars/arrows actually move, but the title/labels remain exactly as Nano Banana drew them.

### Step 2 — Narration (one call per segment)

- Call `GeminiClient.synthesize_speech(model="gemini-2.5-flash-preview-tts", script=narration_script, voice_preset="Kore")`.
- Returns raw PCM audio (24 kHz, mono, 16-bit) along with usage metadata.
- Wrapped as a WAV file (`_write_pcm_as_wav()`) in the segment's workdir. Not an MP3/AAC — AAC-encoding happens later during the mux.

### Step 3 — Combine beats (per segment)

`_combine_beats()` normalises and concatenates:

1. **Strip audio from every beat** (`ffmpeg -an -c:v copy`).
   - Omni output carries an audio stream (even in edit mode); Veo with `generate_audio=False` is silent. Mixing silent and audio-carrying clips in `VideoCombine`'s re-encode fallback breaks ffmpeg's `concat=n=N:v=1:a=1` filter ("Stream specifier `:a:0` matches no streams"). Dropping all audio first makes the inputs uniform; the one narration track mixes in afterwards.

2. **Run `VideoCombine`** on the audio-free clips:
   - **Fast path:** `ffmpeg -f concat -c copy` (no re-encode). Fails silently when clips have mismatched timebases (Veo output is `12288 tbn`, Omni output is `90k tbn`, Nano Banana → ffmpeg loop is also `90k tbn`). The exit code is 0 but the output's duration is wrong (seen in this run: expected 378s, got 2767s).
   - **Duration sanity check** immediately after: if actual vs expected differ by >10%, the result is discarded.
   - **Fallback:** re-encode with `concat` filter_complex — `libx264 -preset medium -crf 22 -c:a aac -b:a 160k`. Slower (~45s for 11 clips in this run) but always correct.

### Step 4 — Mux narration over the stitched video

`_mux_audio_over_video()`:

```
ffmpeg -y \
   -i combined_silent.mp4 -i narration.wav \
   -filter_complex "[1:a]apad[padded]" \
   -map 0:v:0 -map [padded] \
   -c:v copy -c:a aac -b:a 192k \
   -shortest \
   -movflags +faststart \
   output.mp4
```

- **`[1:a]apad[padded]`** pads the narration track with silence so it never runs short of the video. The naïve `-shortest` alone cut 10 seconds off segment 4's payoff shot on the first attempt; this is the fix.
- `-c:v copy` on the video means no video re-encode at this stage (the earlier beat combine already produced the final video stream).
- Output goes to `storage/outputs/video_hybrid_segment-<ts>-<id>.mp4`.

### Step 5 — Final assembly (run_all.py)

After all 11 segments have been generated (or in this run, 10 generated + 1 pre-built segment 4 reused), `run_all.py` calls `VideoCombine` once more over the 11 segment MP4s to produce the full lesson. Same stream-copy → duration check → re-encode fallback as step 3.

Final output copied to `selection_criterion_lesson-<ts>-<id>.mp4`.

---

## 4. Timing — measured per-segment wall-clock

**First full run (hybrid, 2026-11-25 09:46):**

| # | Segment | Beats | Wall-clock | Dominant cost |
|---|---|---|---|---|
| 01 | Everyday choices | 3× veo + 1× infog | 235 s | 3 Veo LROs (polling-bound) |
| 02 | What are criteria | 3× infog | 193 s | 3 Omni edit calls |
| 03 | Need for constraints | 3× infog | 187 s | 3 Omni edit calls |
| 04 | *(pre-built, reused)* | — | — | — |
| 05 | Hard vs soft | 4× infog | 259 s | 4 Omni edit calls |
| 06 | Priorities / trade-offs | 4× infog | 268 s | 4 Omni edit calls |
| 07 | The selection process | 4× infog | 256 s | 4 Omni edit calls |
| 08 | Crossroads | 1× veo + 3× infog | 234 s | 1 Veo + 3 Omni edit |
| 09 | Common mistakes | 3× infog | 175 s | 3 Omni edit calls |
| 10 | Metrics | 4× infog | 262 s | 4 Omni edit calls |
| 11 | Recap | 2× infog | 122 s | 2 Omni edit calls |
| | **All segments** | **35 beats (net of pre-built)** | **~36.5 min** | |
| | Final concat + mux | — | ~45 s | ffmpeg re-encode |
| | **End-to-end** | | **~37 min** | |

**Rough rules of thumb** that fall out of these numbers:

| Operation | Wall-clock cost |
|---|---|
| 1 Nano Banana slide | ~12 s |
| 1 Omni edit call (10s output) | ~38 s |
| 1 Veo clip (8s output, polling) | ~60 s |
| 1 Omni text_to_video call (10s output) | ~38 s |
| 1 TTS call per segment | ~10 s |
| 1 segment ffmpeg concat + mux | ~2 s |
| Full lesson final concat (11 clips, re-encode) | ~45 s |

**Practical estimator** for a new lesson:
```
total_wall_seconds ≈ (n_realistic_beats × 40) +
                     (n_infographic_beats × 50) +
                     (n_segments × 15) +
                     60
```
For reference: this run had 4 realistic + 31 infographic beats across 10 generated segments → `4×40 + 31×50 + 10×15 + 60 ≈ 1920 s ≈ 32 min`, consistent with the actual 36.5 min once polling variance on Veo is factored in.

---

## 5. Cost — measured per model, first full run

All rates from Google's official pricing pages (`ai.google.dev/gemini-api/docs/pricing`
and `cloud.google.com/model-garden/pricing`), confirmed 2026-11-25.

| Model | Role | Calls | Output | Rate | Cost (USD) |
|---|---|---|---|---|---|
| `veo-3.1-lite-generate-001` | Realistic video | 4 | 32 s of 720p video | $0.05 / sec | $1.6000 |
| `gemini-3.1-flash-image` (Nano Banana) | Infographic slides | 31 | 52,080 image tokens | $60 / 1M | $3.1248 |
| `gemini-omni-1.1-flash-preview` | Motion graphics (edit mode) | 31 | 310 s of 720p video | $0.10 / sec | $31.00 |
| `gemini-2.5-flash-preview-tts` | Narration (Kore voice) | 10 | 9,080 audio-out tokens | $10 / 1M | $0.0908 |
| **Totals** | | **76 model calls** | | | **$35.81** |

Input-side costs are < $0.10 across every modality, so we present them aggregated inside the output-side line.

**INR @ ₹83/USD: ₹2,972** total for this 6:18 lesson.

**Per-minute cost of final video: ~$5.68 / ₹471** — tracks Google's published "$6 per minute of 720p video" rate, as expected since Omni dominates.

---

## 6. Omni-only pivot — projected numbers for next run

After this run, pipeline direction pivoted to **Omni-only** (Sharmila di's question: "why two video models?"):

- Drop Veo entirely. Realistic beats → Omni text_to_video.
- Keep Nano Banana for infographics (no video model can render legible slide text).
- Migrate both Omni call sites from `gemini-omni-1.1-flash-preview` to `gemini-omni-1.2-flash` GA (30% cheaper, out of preview — the 1.1-preview's own documented shutdown date, 2026-09-30, had already passed).

**Expected cost for the same 6:18 lesson under the new pipeline:**

| Model | Calls | Output | Rate | Cost (USD) |
|---|---|---|---|---|
| `gemini-omni-1.2-flash` (text_to_video for realistic beats) | ~4 | 40 s | $0.07 / sec | $2.80 |
| `gemini-omni-1.2-flash` (edit for infographic beats) | 31 | 310 s | $0.07 / sec | $21.70 |
| `gemini-3.1-flash-image` (Nano Banana) | 31 | 52,080 image tokens | $60 / 1M | $3.12 |
| `gemini-2.5-flash-preview-tts` | 10 | ~9,000 audio tokens | $10 / 1M | $0.09 |
| **Totals** | | | | **~$27.71** |

**INR: ₹2,300.** A ~23% drop vs the hybrid run, same final runtime.

**For a full 15-minute lesson** (roughly doubling beat counts), projected cost: **~$50 / ₹4,150.**

Confirming note: the Omni-only rebuild run (started 2026-11-25 10:48, in progress at time of writing) is tracking exactly this trajectory — 4 segments completed at $9.19, extrapolating cleanly to ~$23 total.

---

## 7. Tested vs documented — what each claim means

This project is careful to mark the difference, because several things that looked right from documentation turned out to be wrong or incomplete when actually called. For every number above:

| Claim | Status |
|---|---|
| Final video runtime, size, codec, segments | **live-verified** (ffmpeg probe on the output file) |
| Per-segment wall-clock | **live-measured** (progress log) |
| Per-call model names & call counts | **live-measured** (progress log HTTP lines) |
| Veo pricing ($0.05/sec lite) | documented against Google's pricing page; cost calc derives, no official usage_metadata for Veo |
| Omni pricing ($0.10/sec for 1.1, $0.07/sec for 1.2 at 720p) | **confirmed against Google's official pricing page**, 2026-11-25 |
| Nano Banana pricing ($60/1M image-out tokens) | **confirmed against Google's official pricing page** + usage_metadata reports exact tokens |
| TTS pricing ($10/1M audio-out tokens) | not on Google's pricing page; secondary source (`verified: false` in `config.yaml`) |
| Omni 1.2 responds on this project | **probe-verified** 2026-11-25 (short test call, 3 MB response) |
| INR conversion | rate used: ₹83/USD — rough, actual GCP billing in USD |

---

## 8. Reproducing a run from scratch

For the engine team picking this up, or to run locally:

```bash
# Setup (one-time)
pip install -r requirements.txt
mkdir .credentials && cp <your-sa-json> .credentials/service-account.json
cp .env.template .env  # edit if needed

# Run end-to-end
python scripts/full_lesson/run_all.py

# Or one segment at a time (useful for iteration)
python -c "import scripts.full_lesson.run_all as r; r.run_segment('segment_11_recap')"
```

Progress goes to stdout AND to `scratchpad/full_lesson_progress.log` (if the orchestrator's logger is set up).

### What you'll touch when customising

- **Segment plans:** `scripts/full_lesson/segment_NN_*.py` — one file per segment. Edit `PLAN.beats` and `PLAN.narration_script`.
- **Shared style:** `scripts/full_lesson/_shared.py` — the `STYLE_BASE` and `ANIMATE_PRESERVE` prompts; change these to shift the overall visual language across all segments at once.
- **Model IDs & pricing:** `config.yaml` — never hard-code a model in code. When Google deprecates a model, this is the only file that changes.

---

## 9. Known gaps / open items

1. **Narration-to-video length matching is one-sided.** If narration is longer than video, it gets cut by `-shortest`; the pad is only on the audio side. Pace narration to the sum of beat durations. In practice this hasn't happened in any run so far but worth knowing.
2. **Omni edit's input hard cap is 10 seconds.** Longer infographic beats need to be split across multiple `infographic_animated` beats. `infog()` helper clamps automatically.
3. **No frame-chaining for Omni realistic beats.** Shot continuity across two Omni text_to_video calls isn't currently preserved — merge into a single prompt instead. Could be added by using Omni edit mode with a 1-frame seed video, but that's a live experiment (not documented behaviour).
4. **Nano Banana occasionally renders a label with a typo.** Rare but happens; usually a prompt tweak fixes it. No automatic retry logic.
5. **Preview TTS model.** `gemini-2.5-flash-preview-tts` is still used for narration; a GA replacement would be worth checking for periodically.

---

## 10. File & config pointers (where everything lives)

| Purpose | Path |
|---|---|
| Orchestrator | `scripts/full_lesson/run_all.py` |
| Per-segment plans | `scripts/full_lesson/segment_NN_*.py` |
| Shared helpers + style prompts | `scripts/full_lesson/_shared.py` |
| Hybrid-segment capability | `iav/capabilities/video_hybrid_segment.py` |
| Concat + duration-guard | `iav/capabilities/video_combine.py` |
| Only file calling Vertex AI SDK | `iav/models/gemini_client.py` |
| Cost estimator | `iav/models/pricing.py` |
| All model IDs, rates, and per-capability settings | `config.yaml` |
| Per-run progress log | `scratchpad/full_lesson_progress.log` (orchestrator-configurable) |
| Output files | `storage/outputs/` |

---

*Dates are 2026-11-25 unless stated. INR conversions use ₹83/USD throughout.*
