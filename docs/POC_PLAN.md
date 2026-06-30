# Gemini Media Enhancement POC — Planning & Scope

This document captures the refined scope, architecture, and build sequence for the POC, based on the real-world use cases provided by the SME content authoring team and the underlying capability analysis in the feasibility document.

---

## 1. Use cases (refined with real-world context)

### 1.1 Image — hand-drawn diagrams → professional rendering

- **Real-world use**: An SME drafting a question paper hand-draws a diagram (e.g. a trigonometry construction, a circuit, a chemistry structure). They upload it and ask for a professional render.
- **Stakes**: Exam content. Labels, numbers, and geometric relationships must remain exactly correct after rendering — not "artistically reinterpreted".
- **Fit**: Strong. Gemini's Nano Banana Pro is built for high-fidelity image editing with accurate text rendering and instruction following.
- **Pipeline shape**: Single-call image edit via Nano Banana Pro. No draft/finalize split — for exam content, every iteration that isn't the final version is wasted work and the per-image cost difference is rounding error.
- **Human-in-the-loop**: SME (or a reviewer) must sign off on the rendered version before it goes into a question paper. Automated QA alone is insufficient at exam-content stakes.

### 1.2 Audio — two tabs

The original "audio → audio" framing was a hybrid problem because Gemini has no audio-in → audio-out path. With the constraint that the original speaker's voice does **not** need to be preserved (the use case is an English listen-and-repeat test that just needs a consistent professional voice preset), this collapses to a clean TTS pipeline. Two tabs:

**Tab A — Text → Audio**

- Input: a script (text)
- Output: studio-quality MP3 in the chosen voice preset
- Single call to Gemini TTS

**Tab B — Audio → Audio**

- Input: a raw recording
- Pipeline: `recording → Gemini ASR (transcribe) → optional text cleanup → Gemini TTS → output MP3`
- Output: the same content in the chosen voice preset (voice changes from the original speaker — accepted)

Both tabs share the same TTS backend; the only difference is the transcription step at the front of Tab B.

### 1.3 Video → Questions

- **Real-world use**: SMEs author question papers. If they have a lecture or explainer video, they want draft questions and an answer key generated from it that they can then review and edit.
- **Fit**: Strongest of all four. Gemini's video understanding capability is Stable, generally available, and Google's own docs demonstrate this exact workflow as a worked example.
- **Pipeline shape**: Video upload → single call to a general Gemini model with a structured prompt → JSON of questions + answers with timestamp anchors back to the source video.

### 1.4 Video → Professional video

- **Real-world use**: An SME records themselves teaching a topic (informal phone/laptop recording, or a portion of a tutorial). They want it cleaned up to look like proper instructional content.
- **Fit**: Weak for Gemini directly — Gemini cannot edit video. Veo only generates new 8-second clips from scratch.
- **Pipeline shape**: Conventional video post-production (FFmpeg + audio restoration, optionally Topaz) does the actual work. Gemini's role is supporting analysis (text output flagging issues, suggesting cuts).
- **Default POC scope** for "professional": audio cleanup + auto-captions + basic stabilization + light color correction. Tunable once a reference example exists.

---

## 2. Architecture

### 2.1 Guiding principles

- **Model-agnostic abstraction**: Business logic never references a specific Gemini model ID. Model IDs and prompt templates live in `config.yaml`. Google's model deprecation cadence (3 models retired in 2026 alone) makes this non-negotiable.
- **Unified UX**: Every capability follows the same shape — upload file → optional instruction text → process → preview/download. Complexity is hidden in the backend.
- **Production-like quality, POC scope**: Proper module boundaries, config-driven, retry logic, structured logging, type hints. No tests beyond a smoke check per capability for the POC itself.
- **Industry-standard I/O formats**: PNG/JPG for images, MP3/WAV for audio, MP4 for video, JSON for structured output.

### 2.2 Repo layout (planned)

```
iav/
  app.py                       # Streamlit UI, one tab per capability
  config.yaml                  # Model IDs, prompts, params
  capabilities/
    base.py                    # Common interface: process(input, instruction) -> output
    image_enhance.py
    audio_text_to_speech.py
    audio_to_audio.py
    video_to_questions.py
    video_enhance.py
  models/
    gemini_client.py           # Vertex AI SDK wrapper
  storage/                     # Local file I/O for POC (swap later)
  docs/
  requirements.txt
  .credentials/                # Gitignored. Service account JSON dropped here.
```

### 2.3 Authentication

- Google Cloud service account JSON (project ID, private key, etc.)
- Auth path: **Vertex AI**, not the Gemini Developer API
- SDK: `google-genai` with `vertexai=True`
- Credentials file lives at `.credentials/service-account.json` (gitignored). `GOOGLE_APPLICATION_CREDENTIALS` points to it.

### 2.4 Privacy / tier

- All calls run on the **paid tier** (Vertex AI billing account). Free-tier traffic is used to improve Google's products and is unacceptable for any real exam content.

---

## 3. Build sequence

| Phase | Deliverable | Why this order |
|---|---|---|
| 0 | Repo scaffold, Streamlit shell, Vertex AI client wrapper, config | Foundation reused by every capability |
| 1 | **Image enhancement** | Strongest fit, simplest pipeline, validates the whole stack end-to-end |
| 2 | **Audio — both tabs** | Shared TTS backend; Tab A is trivial once the client works, Tab B adds the ASR step |
| 3 | **Video → Questions** | Single Gemini call, structured prompt; reuses scaffold |
| 4 | **Video → Professional** | Most complex (FFmpeg + audio reuse + Gemini analysis), saved for last |

---

## 4. Open items / decisions still pending

- **Confidentiality sign-off** for pre-release exam content going to a third-party API. Required from whoever owns exam integrity before real exam content touches the POC.
- **Voice preset choice** for the audio use cases — needs validation by whoever owns the English curriculum (accent, gender, pace, formality).
- **Reference example** for "professional video" — none yet. POC defaults to audio cleanup + captions + stabilization + light color correction.
- **Volume estimates** per use case — needed to model real monthly cost before scaling beyond the POC.
- **Sample inputs** — to be provided as each capability is built: hand-drawn diagram for image, script + raw recording for audio, short SME-style video for the video capabilities.

---

## 5. Out of scope for the POC

- Integration with the actual content authoring engine (engine team handles that against the POC's API/UI)
- Authentication, multi-tenant identity, audit logs (POC runs locally for one user)
- Production deployment, scaling, queueing, async job orchestration for video generation (deferred — POC handles long-running video calls inline with a clear progress indicator)
- Caching / batch API cost optimizations (correctness first; optimize after the POC validates the approach)
