# IAV — Gemini Media Enhancement POC (HOELT)

This is a Streamlit proof-of-concept built for **HOELT**, demonstrating
Gemini/Vertex AI (and, for some capabilities, Azure as a fallback) for
SME content-authoring workflows: turning hand-drawn diagrams, raw
recordings, and short scenario briefs into exam-ready images, audio, and
video, plus deriving comprehension questions from existing content.

The engine team that picks this up next should be able to get fully
oriented from this file plus `docs/` — nothing about what's been built,
tested, or found broken should require re-deriving from scratch or asking
the person who built it.

**Read `docs/VIDEO_CAPABILITIES.md` before touching anything video-related.**
It has the full story — what was broken, what was wrong even after the
first fix, what's live-verified vs. merely documented, and the design for
the long-form video work that's next. This file (`CLAUDE.md`) only
summarizes it.

**For the long-form lesson work specifically** (the "Selection Criterion"
TCS iON concept video and everything that built off it), the two
Selection Criterion docs are the authoritative handoff:

- `docs/SELECTION_CRITERION_PIPELINE_DEEP_DIVE.md` — the engineering
  reference: pipeline architecture, step-by-step mechanics, timing and
  cost measurements for BOTH runs (hybrid and Omni-only), scaling
  projections, recommendations. Read this when you're doing engine work
  on long-form lessons.
- `docs/SELECTION_CRITERION_RUN_METADATA.md` — the stakeholder-facing
  summary of the same work (shorter, less code-oriented). Share with
  non-engineering readers.

**Important pipeline change as of 2026-11-25:** Long-form lessons pivoted
from the hybrid (Veo + Nano Banana + Omni) pipeline to Omni-only (Nano
Banana + `gemini-omni-1.2-flash` GA + TTS), ~33% cheaper and single-video-
model. Veo is no longer called by any live lesson-generation path in
this repo, though the `veo` beat kind and the Veo capabilities are still
present for backward compatibility and for anything else that wants
realistic cinematic footage. See the deep-dive doc §5 and §6 for the
numbers.

---

## 1. What this app actually is

A single-user Streamlit shell (`app.py`) plus a second, video-only
Streamlit shell (`video_studio.py`) over a shared backend
(`iav/capabilities/`, `iav/models/`, `iav/storage/`). Every capability
implements one interface (`Capability.process(CapabilityInput) ->
CapabilityOutput`, in `iav/capabilities/base.py`) so the UI, cost
tracking, and storage layer never need to know which capability or model
they're talking to.

**Golden rule, enforced everywhere in this codebase:** business logic
never references a model ID directly. Model IDs, prompts, and every
per-capability parameter live in `config.yaml`. When Google deprecates a
model (it has, more than once, during this project), that's a config
edit, not a code change.

### Why two separate Streamlit apps

`app.py` is the original, full-capability shell. Three of its tabs are
currently **hidden** (`SHOW_GENERATE_VIDEO`, `SHOW_VIDEO_TRANSFORM_TABS`,
`SHOW_TEXT_TO_SPEECH_TAB` are all `False` near the top of `app.py`) —
the capability code behind them is real and working, they're just not
surfaced in the main demo UI. `video_studio.py` exists specifically
because video had no demo surface at all: it's a standalone app
(`streamlit run video_studio.py`) consolidating every video capability
into one place, built so Gemini Omni's video-to-video and the clip-combine
work could actually be shown to stakeholders. See
`docs/VIDEO_CAPABILITIES.md` for why each tab is hidden and what it'd take
to un-hide them.

---

## 2. Repo layout

```
app.py                      Main Streamlit shell (image/audio tabs active;
                             3 video-related tabs present but hidden)
video_studio.py              Standalone Streamlit shell, every video
                             capability, nothing hidden
config.yaml                   Every model ID, prompt template, and
                             per-capability parameter. Read this before
                             reading the capability code -- it explains
                             *why* each value is what it is, with dated
                             comments recording what was live-tested.
requirements.txt

iav/
  capabilities/              One file per capability (see table below),
                             all implementing Capability.process()
    base.py                  Capability / CapabilityInput / CapabilityOutput
    prompt_schema.py         Shared CommonAttributes + validation for every
                             "generate from scratch" capability
    _json_utils.py           Loose JSON parsing for model output that
                             should be structured but isn't always clean
  models/
    gemini_client.py         The ONLY thing that calls the Vertex AI SDK.
                             Every Gemini/Veo/Omni call in the app goes
                             through this one wrapper.
    azure_openai_client.py,
    azure_speech_client.py    Azure fallback paths for text/image and TTS
    config.py                 Loads config.yaml + env vars into typed settings
    pricing.py                 Turns token/duration usage into an estimated
                             cost; also the thing that silently reports
                             $0.00 if a model's pricing key doesn't exactly
                             match what's actually being called (this has
                             bitten this project twice -- see Section 5)
  storage/
    local.py                  save_input / save_output / output_path --
                             local filesystem for the POC, swap for cloud
                             storage before anything production-facing

docs/
  POC_PLAN.md                 The ORIGINAL planning doc. Historical --
                             written before video generation, video-to-
                             video, clip-combining, or long-form video
                             existed. Useful for the original use-case
                             framing and architecture rationale; not
                             current on capability status.
  VIDEO_CAPABILITIES.md       The full depth on every video capability:
                             what's live-verified, what's only documented,
                             every bug found and fixed, and the design for
                             what's next. Read this, not just this file,
                             before doing video work.
  SELECTION_CRITERION_PIPELINE_DEEP_DIVE.md
                             Engineering reference for the long-form
                             lesson pipeline (TCS iON "Selection
                             Criterion" video, 2026-11-25): architecture,
                             step-by-step mechanics, measured timing +
                             cost for both the hybrid run ($35.81) and
                             the Omni-only rebuild ($24.05), scaling
                             projections, and the recommendation to use
                             Omni-only going forward.
  SELECTION_CRITERION_RUN_METADATA.md
                             Stakeholder-facing summary of the same
                             work. Shorter, less code-oriented -- for
                             sharing with non-engineering readers.

scripts/
  full_lesson/                 The Selection Criterion long-form lesson
                             pipeline (lives here rather than iav/ because
                             the segment plans are content, not generic
                             capability code -- iav/capabilities/video_
                             hybrid_segment.py is the generic building
                             block it drives).
    run_all.py                 Orchestrator: runs all 11 segments then
                             assembles the final lesson.
    _shared.py                 Shared style prompts + the omni_real() /
                             infog() / veo() beat helpers.
    segment_NN_*.py            One file per segment: title + beats +
                             narration_script.
    segment_01_omni_only.py    Standalone test: segment 1 regenerated
                             with pure Omni (no Nano Banana). Kept as
                             reference for why Nano Banana can't be
                             dropped -- see the deep-dive doc.

.credentials/                 Gitignored. Service account JSON goes here.
.env                           Gitignored. See Section 6.
```

---

## 3. Capability inventory — current status

| Capability | File | What it does | Status |
|---|---|---|---|
| Image Enhance | `image_enhance.py` | Hand-drawn diagram → professional render (Nano Banana Pro) | Working, active in `app.py` |
| Generate Image | `image_generate.py` | Structured prompt → new exam-question image | Working, active in `app.py` |
| Text → Audio | `audio_text_to_speech.py` | Script → studio narration (Gemini TTS) | Working, **hidden** (`SHOW_TEXT_TO_SPEECH_TAB=False`) — superseded in the UI by Audio-to-Audio's "write from scratch" mode |
| Audio → Audio | `audio_to_audio.py` | Recording → transcript → re-narrated audio, or write-from-scratch | Working, active in `app.py` |
| Generate Audio | `audio_generate.py` | Structured prompt → new narrated audio | Working, active in `app.py` |
| Audio → Questions | `audio_question_generation.py` | Topic/passage → narrated audio + comprehension questions | Working, active in `app.py` |
| Generate Video | `video_generate.py` | Text prompt → new clip (Veo 3.1) | Working. Hidden in `app.py` (`SHOW_GENERATE_VIDEO=False`); active in `video_studio.py` |
| Video → Video | `video_edit.py` | Edit/extend existing footage — Veo Extend (own output only) + Gemini Omni edit/extend (arbitrary footage) | Working. Only reachable via `video_studio.py` — never had a home in `app.py` |
| Combine Clips | `video_combine.py` | Several clips → one longer file (ffmpeg) | Working. Only reachable via `video_studio.py` |
| Video → Questions | `video_to_questions.py` | Video → structured comprehension questions | Working, **hidden** in `app.py` (`SHOW_VIDEO_TRANSFORM_TABS=False`); active in `video_studio.py` |
| Video → Professional | `video_enhance.py` | SME recording → stabilised/captioned/denoised MP4 (ffmpeg + Gemini transcription) | Working, **hidden** in `app.py`; active in `video_studio.py` |
| Long-form hybrid segment | `video_hybrid_segment.py` | One educational-video segment composed from realistic, static-infographic, animated-infographic beats + narration | Working. Driven by `scripts/full_lesson/` for the Selection Criterion lesson |
| Full lesson (Selection Criterion) | `scripts/full_lesson/run_all.py` | 11-segment lesson: segment plans → per-segment hybrid-segment capability → ffmpeg final assembly | **Built and shipped twice** (2026-11-25) — see `docs/SELECTION_CRITERION_PIPELINE_DEEP_DIVE.md` |
| Topic → full video utility | *not built yet* | Topic + target duration → LLM-written segment plans → full video | **Designed, not built** — planned extension of the Selection Criterion pipeline |

"Working" means live-tested against the real Vertex AI project this POC
runs on, not just read for correctness — every capability above has been
run for real at least once with real output inspected.

---

## 4. Running it

```bash
pip install -r requirements.txt
streamlit run app.py             # main shell: image + audio tabs
streamlit run video_studio.py    # video-only shell: every video capability
```

Both need the same `.env` / `.credentials/service-account.json` — see
Section 6.

---

## 5. Things that will bite you if you don't know them

These are patterns that have caused real, live bugs in this project more
than once — worth internalizing, not just reading once:

1. **Pricing-key drift.** `config.yaml`'s `pricing.models` is keyed by
   exact model name string. When a model ID changes (Google deprecates
   one, or a capability's config is updated to a new model), the pricing
   table doesn't automatically follow — cost silently reports **$0.00**
   for a real, billed call instead of erroring. This has happened at
   least twice in this project (a `gpt-4.1` deployment-name mismatch, and
   the entire Veo `-preview` → GA model rename). Whenever a model ID
   changes anywhere, check the pricing table changed with it.
2. **Region behavior is not consistent across model families, and it's
   not symmetric with what you'd guess.** Veo has no `global` support at
   all and only works on `us-central1` on this project (EU regions 404
   despite being listed as available in Google's own docs). Gemini
   Omni's Interactions API is the opposite: `us-central1` fails outright,
   only `global` works. Get this backwards and the error looks like a
   permissions problem, not a region problem.
3. **A clean exit code is not proof of a correct result.** Found twice
   this project: (a) Gemini Omni's Interactions API returning a 404 for
   a request-shape problem that read exactly like a missing IAM
   permission — it wasn't; (b) `ffmpeg`'s concat demuxer exiting 0 while
   silently producing a video with a *wrong duration* when two input
   clips had incompatible timebases. Both are now specifically guarded
   against in code (see `video_edit.py`'s input-shape handling and
   `video_combine.py`'s post-concat duration check) — the pattern to
   generalize: a successful-looking response from an external API or
   tool is not the same thing as a verified-correct one.
4. **"Documented" and "live-verified" are not the same claim, and this
   codebase is careful to mark the difference** (see comments throughout
   `config.yaml` and all of `docs/VIDEO_CAPABILITIES.md`). Keep doing
   that. Several things that looked right from Google's own
   documentation turned out to be wrong or incomplete once actually
   called — don't present a documentation read as a tested fact.

---

## 6. Environment

Only Google/Vertex AI credentials matter for any Gemini/Veo/Omni
capability — none of them use Azure. Azure is used only by some audio/
image capabilities as a configurable fallback vendor (see `app.py`'s
vendor selector).

```bash
# Required: path to the GCP service account JSON (the actual credential)
GOOGLE_APPLICATION_CREDENTIALS=.credentials/service-account.json

# Optional -- project_id/location auto-read from the service account
# JSON if omitted:
# VERTEX_AI_PROJECT_ID=...
# VERTEX_AI_LOCATION=global

LOG_LEVEL=INFO
```

`.credentials/service-account.json` is gitignored and must be supplied
separately — it is never committed.

---

## 7. Where the business-facing documents live

Two documents were produced for non-engineering stakeholders during the
video work and are **not** in this repo (they live in Claude's Docs/
Artifact system, tied to the session that made them, not to this git
history):

- A technical reference (Word .docx) covering every video capability:
  model options, input/output, cost, region, concurrency per use case,
  plus the long-form video approach.
- A business-framed live doc (Claude Docs) for non-technical stakeholders,
  covering the same ground in plain language.

Both were kept in sync with the real implementation as of when they were
last updated, but **this repo — `CLAUDE.md` + `docs/VIDEO_CAPABILITIES.md`
— is the source of truth going forward.** If those external documents and
this repo ever disagree, trust the repo and update the external docs, not
the other way around.

---

## 8. Open items / known gaps

- Gemini Omni's prompt-to-video path (text-to-video) is now **wired
  into `video_hybrid_segment.py`** via the `omni_realistic` beat kind
  (2026-11-25 pivot) — this was previously an open item.
- `gemini-2.5-pro` works for `video_to_questions` (live-verified) but
  isn't in that capability's `available_models` list in `config.yaml` yet
  — a one-line config addition, not a code change.
- **Omni GA now reachable** on this project. As of 2026-11-25, the
  pipeline uses `gemini-omni-1.2-flash` GA (probe-verified + 34 live
  calls across Run B of the Selection Criterion lesson). The older
  `gemini-omni-1.1-flash-preview` whose shutdown date had passed is no
  longer the default, though it's kept in `available_omni_models` for
  rollback. The `gemini-omni-1.1-flash` GA name (no suffix) was still
  rejected last time it was tried — hasn't been re-checked since 1.2
  came online; no immediate need to.
- Veo Extend has been observed to reject a specific prior clip outright,
  for reasons not surfaced by the API, on at least one real clip during
  testing — confirmed not a region issue (the same clip worked in another
  region). Not a bug in this codebase; the error is surfaced cleanly, not
  silently swallowed, but worth knowing it can happen in a live demo.
- **Hand-authored long-form lesson is built** — the Selection Criterion
  lesson (11 segments, ~6 min) ships end-to-end via
  `scripts/full_lesson/run_all.py` and was produced twice (hybrid +
  Omni-only); see `docs/SELECTION_CRITERION_PIPELINE_DEEP_DIVE.md` for
  the measured numbers. The remaining open item is the generic
  **topic → full video utility**: give it a topic and a target
  duration, and have an LLM write the segment plans that the existing
  pipeline then renders. Designed in `docs/VIDEO_CAPABILITIES.md`,
  not built.
