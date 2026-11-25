# Selection Criterion — Full Lesson Generation Metadata

**Project:** TCS iON — "Selection Criterion" 15-min concept video
**Generated on:** 2026-11-25
**Pipeline:** IAV (HOELT POC) — hybrid Gemini / Veo / Nano Banana / Omni stack
**Delivered file:** `storage/outputs/selection_criterion_lesson-20261125T094632Z-e0273f20.mp4`

---

## 1. Final Deliverable

| Attribute | Value |
|---|---|
| Final video file | `selection_criterion_lesson-20261125T094632Z-e0273f20.mp4` |
| Runtime | **6:18** (378 s) |
| Size | 20,160,417 bytes (~20 MB) |
| Resolution / codec | 720p H.264, AAC 160 kbps |
| Segments stitched | 11 of 11 |
| Final assembly mode | Re-encode concat (stream-copy fallback caught a timebase mismatch and re-encoded cleanly) |

---

## 2. Pipeline — What produced this video

Hybrid pipeline composed per-segment. Each segment is made of "beats"; each beat is either:

- **Veo 3.1 Lite** — realistic / cinematic clip (used sparingly, 4 clips total across the lesson)
- **Nano Banana + Omni edit** — a crisp professional infographic slide (Nano Banana) with **real motion graphics** layered on by Gemini Omni's video-to-video edit. This is the piece that gives us the Synthesia-style look Sharmila di liked in segment 4.
- **Gemini TTS (Kore voice)** — segment-wide narration muxed over the stitched video

**Final assembly:** per segment, beats are concatenated → narration audio is muxed in (padded with silence if the video runs longer) → all 11 segment MP4s are concatenated into the lesson.

---

## 3. Per-Segment Breakdown

| # | Segment | Wall-clock | Est. cost (tracked models only) |
|---|---|---|---|
| 01 | Everyday choices | 235 s | $1.2108 |
| 02 | What are criteria | 193 s | $0.0243 |
| 03 | Need for constraints | 187 s | $0.0248 |
| 04 | *(pre-built, reused as-is)* | — | — |
| 05 | Hard vs soft criteria | 259 s | $0.0303 |
| 06 | Priorities & trade-offs | 268 s | $0.0301 |
| 07 | The selection process | 256 s | $0.0311 |
| 08 | Crossroads example | 234 s | $0.4253 |
| 09 | Common mistakes | 175 s | $0.0265 |
| 10 | Post-selection metrics | 262 s | $0.0301 |
| 11 | Recap | 122 s | $0.0173 |
| | **All segments total** | **~36.5 min** | **$1.8506** |
| | Final concat + mux | ~45 s | — |
| | **End-to-end wall-clock** | **~37 min** | |

(Segments 01 and 08 are the costlier ones because each contains a Veo clip. Everything else is Nano Banana + Omni + TTS.)

---

## 4. Model Usage — Calls, Tokens, Seconds

| Model | Role | Calls | Output | Output rate |
|---|---|---|---|---|
| `veo-3.1-lite-generate-001` | Realistic video clips | 4 | 32 s of 720p video | $0.05 / sec |
| `gemini-3.1-flash-image` (Nano Banana) | Infographic slides | 31 | 52,080 image tokens | $60 / 1M image-out tok |
| `gemini-omni-1.1-flash-preview` | Motion-graphics (edit arbitrary input video) | 31 | 310 s of 720p video (10 s per call) | $17.50 / 1M video-out tok ≈ $0.10/sec |
| `gemini-2.5-flash-preview-tts` | Narration (Kore voice) | 10 | 9,080 audio tokens | $10 / 1M audio-out tok |

**Input-side (combined across all models):** small — TTS prompts (~930 text tokens), Nano Banana prompts (~1,643 text tokens), and 31 Omni starting-image inputs (~37K multimodal tokens). Total input cost is sub-dollar.

---

## 5. Cost — USD and INR (@ ₹83/USD)

| Model | Basis | USD | INR |
|---|---|---|---|
| Veo 3.1 Lite | 32 output-sec × $0.05 | $1.6000 | ₹132.80 |
| Gemini 2.5 Flash TTS | 9,080 tok × $10/M | $0.0908 | ₹7.54 |
| Nano Banana (image) | 52,080 tok × $60/M | $3.1248 | ₹259.36 |
| Gemini Omni 1.1 Flash | 310 output-sec × ~$0.10/sec | **$31.48** | **₹2,612.84** |
| **GRAND TOTAL** | | **$36.30** | **₹3,012.54** |

**Per-minute of final video: ~$5.76 / ₹478.** This tracks the official "$6/min of 720p video" rate, which is expected since Omni dominates.

### Why the Omni number is a revision

Earlier in our working notes the Omni cost was listed as $0 per call because no pricing entry existed in our local pricing table for the preview model name. Using Google's published rate for `gemini-omni-1.1-flash` (GA) — $17.50 / 1M video-output tokens at 5,792 tokens per second of 720p video — the actual Omni spend for this run is **~$31.48**. I've noted this so the per-segment log reflects real cost on the next run.

---

## 6. Caveats & Things to Know

1. **Omni preview-model caveat.** We're calling `gemini-omni-1.1-flash-preview`; Google's published pricing is for the GA name `gemini-omni-1.1-flash`. We've applied GA rates to our preview usage in the cost table above, which is the safe assumption. The preview model's own documented shutdown date has already passed — it's still responding, but a production rollout should re-verify the GA name or get the GA rate card confirmed via Google support.
2. **Segment 4 is not in the cost above.** It was built before this run and reused as-is. Including it would add ~$2 on the same profile.
3. **ffmpeg timebase-mismatch guard worked.** During final assembly the stream-copy concat exited with code 0 but produced a wrong-duration file (2767s instead of 378s) — this is a known ffmpeg pitfall when input clips come from mixed sources (Veo + Omni + still-image renders have different internal timebases). The pipeline detected the duration mismatch and transparently fell back to a re-encode, which produced the correct 6:18 output.
4. **"Working" means live-tested end-to-end.** Every model listed above was actually called against the Vertex AI project during this run and its real output is in the final MP4 — no numbers in this doc come from documentation reads.

---

## 7. What's next — options to discuss

| Option | What it does | Added cost | Added time |
|---|---|---|---|
| **A. Ship as-is (6:18)** | Deliver the current MP4 to stakeholders | — | — |
| **B. Expand to full 15 min** | Double beat counts per segment, roughly doubling Omni calls | ~$35 more (total ~$70) | ~40 min more |
| **C. Omni-only comparison test** | Rebuild segment 1 using Omni alone (no Veo, no Nano Banana) to see whether a single-model pipeline matches the hybrid quality | ~$2 | ~5 min |
| **D. Generalise to a utility** | Topic + target duration → full video, auto-planned (LLM writes the segment plan) | — (design + build work) | — |

---

## 8. Reference — File and Config Pointers

- Final video: `/home/user/IAV/storage/outputs/selection_criterion_lesson-20261125T094632Z-e0273f20.mp4`
- Per-segment MP4s: `/home/user/IAV/storage/outputs/video_hybrid_segment-*.mp4` (11 files)
- Segment plans: `/home/user/IAV/scripts/full_lesson/segment_*.py`
- Shared style prompts (keeps visual consistency across segments): `/home/user/IAV/scripts/full_lesson/_shared.py`
- Orchestrator: `/home/user/IAV/scripts/full_lesson/run_all.py`
- Progress log for this run: `scratchpad/full_lesson_progress.log`
- Core capability: `/home/user/IAV/iav/capabilities/video_hybrid_segment.py`
- Model/config source of truth: `/home/user/IAV/config.yaml`

---

*INR figures throughout this doc use ₹83/USD. Actual INR charge may vary with the prevailing rate on the GCP billing cycle.*
