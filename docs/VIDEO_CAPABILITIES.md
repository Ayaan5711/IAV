# Video Capabilities — Full Reference

Everything built, tested, found broken, and fixed on the video side of
this POC, in enough depth that a fresh session can pick up exactly where
this left off without re-deriving any of it. Facts are marked
**(live-verified)** where confirmed by actually calling the API against
this project's real credentials, and **(documented)** where sourced from
Google's own materials but not independently tested here — this
distinction is kept throughout because several "documented" claims in
this project turned out to be wrong or incomplete once actually tested
(see §7).

---

## 1. The four use cases

| Use case | What it means | Capability | Status |
|---|---|---|---|
| Prompt → Video | Generate a new clip from a text description | `video_generate.py` | Working |
| Video → Video | Edit or extend footage that already exists | `video_edit.py` | Working |
| Prompt → Video → Question | Generate a clip, then auto-generate comprehension questions from it | Generate tab → Questions tab (2 manual steps today) | Working |
| Video → Question | Generate comprehension questions from existing footage, no generation step | `video_to_questions.py` | Working (pre-existing before this round of work) |

Plus a fifth, cross-cutting need that came up directly from a real
requirement ("can we generate multiple videos and combine them with
ffmpeg for a longer educational video?"): **Combine Clips**
(`video_combine.py`).

All five are reachable from `video_studio.py` (`streamlit run
video_studio.py`) and have been run end-to-end through a real browser —
real file uploads, real API calls, real results inspected — not just
read for correctness.

---

## 2. Root cause: why video generation looked broken in the first place

The original symptom was 404s on every `video_generate` call. The actual
cause **(live-verified)**: `config.yaml` pointed at three Veo model IDs —
`veo-3.1-generate-preview`, `veo-3.1-fast-generate-preview`,
`veo-3.1-lite-generate-preview` — that had been deprecated with a
**2026-04-02 migration deadline** and now 404 unconditionally. The region
pin (`us-central1`) was *not* the problem; it was already correct.

Fixed in `config.yaml`: model IDs moved to the GA names
(`veo-3.1-generate-001`, `-fast-`, `-lite-`), `available_locations`
narrowed to just `us-central1` (the only region confirmed to work — EU
regions 404 despite being listed as available in Google's own docs).

Two more real bugs this surfaced, both fixed:

1. **Cost tracking silently reported $0.00** for a real, billed call —
   `pricing.models` was still keyed to the deprecated `-preview` names.
   Re-keyed to the GA names with corrected per-second rates. This is the
   same class of bug as an earlier `gpt-4.1` pricing-key mismatch found
   elsewhere in this project — see `CLAUDE.md` §5 for the general
   pattern.
2. **A live SDK deprecation warning** on every submission —
   `generate_videos(prompt=..., config=...)` was flagged for removal
   (deadline already passed). Migrated to the current calling convention,
   `generate_videos(source=GenerateVideosSource(prompt=...), config=...)`.

---

## 3. Veo 3.1 — the three tiers

| Model | Status | Duration | Resolution | Reference images | Price/sec |
|---|---|---|---|---|---|
| `veo-3.1-generate-001` | GA | 4, 6, or 8 sec | 720p, 1080p (4K upscale needs separate Google allowlist) | Up to 3 | $0.20 |
| `veo-3.1-fast-generate-001` | GA | 4, 6, or 8 sec | Same | Up to 3 | $0.10 |
| `veo-3.1-lite-generate-001` | **Preview** (despite the `-001` suffix — don't infer GA status from the ID format) | 4, 6, or 8 sec | Same | Not supported | $0.05 (720p) / $0.08 (1080p) |

**Region: `us-central1` only (live-verified).** No `global` support at
all, unlike every other Gemini model in this app — the opposite of
Gemini Omni (§4). Get this backwards and the symptom looks like a
permissions problem, not a region one.

**Rate limits (documented):** GA tiers 50 req/min. Preview (lite tier)
10 req/min, 10 concurrent max.

**Veo Extend** (continuing Veo's own prior output): same
`generate_videos` call, with the prior clip's bytes passed as
`GenerateVideosSource.video` instead of (or alongside) a prompt.
**(Live-verified):** generated a clip, extended it, got back a real
clip grown from 946KB to 2.87MB — consistent with the documented
7-second addition. Up to 20 chained extensions, 148 seconds (~2.5 min)
total — Google's documented ceiling, only one hop independently
chained here. Output stays capped at 720p regardless of source
resolution. **This only continues Veo's own output** — it cannot take
an arbitrary uploaded clip.

**Observed quirk:** Veo Extend rejected one specific prior clip outright
during testing, with no video in the response and no `operation.error`
set — confirmed this wasn't a region issue (the same clip succeeded via
both `us-central1` and `global` in isolation testing). Not a bug in this
codebase's handling — the rejection surfaces as a clean
`GeminiCallError`, not a crash or a silent wrong result — but worth
knowing a specific clip can be rejected for reasons the API doesn't
explain.

---

## 4. Gemini Omni 1.1 Flash — video-to-video on ARBITRARY footage

This is the capability that lets you edit or extend footage the app
never generated itself — not just Veo's own prior output. Getting here
took real, documented wrong turns, kept below rather than collapsed to
just the final answer, because the wrong intermediate conclusion is
exactly the kind of thing a shallower pass would have stopped at and
reported as final.

### 4.1 The wrong turn: an IAM-permissions theory that wasn't true

Every early attempt at Omni video output failed with `404 Requested
entity was not found` — using a **flat** input list shape:
`input=[{"type": "text", "text": "..."}]`. Text-only calls succeeded in
this shape; anything requesting video, image, or audio output failed
identically. That pattern (one modality works, others fail the same way)
looked exactly like a missing IAM role on the service account used by
this app, versus a human's own interactive sign-in (which the user
separately confirmed worked, via the Cloud Console). That theory was
written up, reported, and was **wrong**.

### 4.2 The actual fix: input shape, not permissions

The SDK's own type signature allows two different shapes for the
`input` parameter: `InteractionsInputParam = Union[ContentParam,
List[StepParam], List[ContentParam], str]`. The flat shape above matches
`List[ContentParam]` — valid, but only works for text output on this
account. The other shape, wrapping content in a `user_input` step
(`input=[{"type": "user_input", "content": [...]}]`, matching
`List[StepParam]`), is the one that actually works for non-text output.
**(Live-verified):** switching only the input shape — same credentials,
same project, zero config or IAM changes — made a real video generation
succeed immediately. The 404s were never a permissions problem; they
were the API's generic error for "this input shape isn't valid for this
modality," which looks exactly like a missing-permission error and
isn't one.

**The general lesson, worth generalizing beyond this one bug:** when a
documented capability keeps failing in a way that looks like
access/permissions, re-examine request *shape* before concluding
something is blocked — this is now `gemini_client.py`'s
`interactions_video()`'s own docstring, not just this file.

### 4.3 Confirmed working (this account, wrapped input shape)

- **Text** (either input shape works for text).
- **Video, text-to-video** (`generation_config.video_config.task=
  "text_to_video"`, no `response_modalities` needed).
- **Video, edit** (`task="edit"`) — transforms an arbitrary uploaded clip
  per an instruction. **Live-verified on footage from a completely
  different pipeline** (a Veo-generated clip, not Omni's own output) —
  this was deliberately tested to rule out Omni just recognizing/
  continuing its own prior generations.
- **Video, extend** (`task="extend"`) — continues an arbitrary uploaded
  clip. Same arbitrary-footage verification as edit.

### 4.4 Confirmed NOT working (this account)

- **Image and audio generation** — explicitly requesting
  `response_modalities=["image"]` or `["audio"]` 404s every time, with
  the corrected input shape too. Omitting `response_modalities` and only
  setting `generation_config.image_config`/`audio_config` doesn't error,
  but doesn't reliably return the requested modality either (one run
  returned an unrelated video for an image request; another returned
  plain text for an audio request) — **don't treat this as a working
  path**, treat image/audio as genuinely unavailable here, not as a
  config problem to keep tuning.
- **Input duration is capped at 10 seconds — live-verified as a hard
  limit, not just documented.** Fed an 11-second clip (a Veo clip plus
  one Veo extension) to `edit`; got back a precise rejection:
  `"Editing duration 11 exceeds maximum duration 10."` Clips of 10
  seconds or less work fine. This means Omni **cannot** be used to build
  long videos by repeated chaining the way Veo's own Extend can — once a
  clip passes 10 seconds, no further Omni edit/extend call will accept it
  as input. (See §8 for how long-form video generation works around this
  entirely, by not using Omni's chaining at all.)

### 4.5 Region — the opposite of Veo

**`global` only (live-verified).** `us-central1` fails outright for Omni
— the exact reverse of Veo's region requirement (§3). The two model
families do not share a region story; this is worth remembering
specifically because it's counter-intuitive.

### 4.6 Model name risk — flag before relying on this for anything real

Everything above only works through the **preview-named model**
(`gemini-omni-1.1-flash-preview`). The GA name (`gemini-omni-1.1-flash`,
no suffix) is **rejected outright** on this account:
`400 "Unsupported model interaction"` — confirmed directly, not assumed.
Google's own documentation lists that preview model's shutdown date as
**2026-09-30**, which has already passed as of this writing; it's still
responding, but that could stop at any time without warning. **This
needs a resolution with Google** — either get the GA name working on
this account, or get clarity on how long the preview name will keep
responding — before anything built on Omni goes to production.

### 4.7 Concurrency / rate limits

Not documented by Google in an easily-citable way, and not independently
load-tested here. Open question — flag it rather than guess a number.

---

## 5. `video_edit.py` — wiring both mechanisms into real code

Both of §3's Veo Extend and §4's Omni edit/extend were tested via
standalone scripts before this capability existed. `video_edit.py` +
two new `GeminiClient` methods (`extend_video()`, `interactions_video()`)
wire both into the app's actual capability layer, reachable from
`video_studio.py`'s Edit/Extend tab.

- `extend_video()` reuses `generate_video()`'s submit-then-poll
  long-running-operation flow (factored out into a shared
  `_run_video_operation()` helper rather than duplicated).
- `interactions_video()` implements the `user_input`-wrapped shape from
  §4.2, synchronous (no polling — Omni's Interactions API returns
  complete, unlike Veo's long-running operations).
- Mode selection (`veo_extend` / `omni_edit` / `omni_extend`) is a single
  `params["mode"]` string; the UI shows the preview-model risk (§4.6)
  inline whenever an Omni mode is selected, not buried in a separate doc.
- Omni calls report `$0`/unverified cost with a clear note (no published
  pricing exists yet for this model) rather than inventing a rate.
- Veo Extend pins `location: us-central1` to match `video_generate`'s
  established, tested-safe region, even though one ad-hoc test against
  `global` happened to succeed — not worth trusting a one-off success
  over the extensively-tested pin.

All three modes (`veo_extend`, `omni_edit`, `omni_extend`) are
live-verified through this actual capability class, not just the
standalone scripts that preceded it.

---

## 6. `video_combine.py` — building longer videos from several clips

Answers the real requirement: "can we generate multiple videos and
combine them with ffmpeg to make a proper long-form video?" Yes — and
ffmpeg was already a hard dependency of this app (`video_enhance.py`
already requires and shells out to it), so this is the same established
pattern, not a new dependency.

Two paths, picked automatically:

- **Stream-copy** (`-c copy`): lossless, near-instant, when clips share
  codec/resolution/frame rate.
- **Re-encode**: works even when clips differ, slower.

### A real bug this caught

Concatenating a Veo-generated clip with a Gemini-Omni-generated clip
**exited 0** via the stream-copy path but silently produced a file
reporting **2:33 of duration instead of the real ~21 seconds** —
incompatible timebases between the two generation pipelines, invisible
from the exit code alone. (The official ffmpeg concat-demuxer docs do
say "all files must have the same streams — same codecs, same time
base, etc." — this project's tooling just hadn't verified that was
actually being honored.) **Fixed** by probing the output's actual
duration (parsed from `ffmpeg`'s own stderr banner, no `ffprobe`
dependency assumed) and comparing it against the sum of the inputs'
durations before trusting the stream-copy result; falls back to the
re-encode path if the numbers don't match within tolerance. Re-verified
correct afterward (21.03s, matching 11.00 + 10.03 exactly).

**The general lesson:** a tool exiting 0 is not proof its output is
correct — see `CLAUDE.md` §5 for why this is called out as a repo-wide
pattern, not a one-off.

---

## 7. `video_studio.py` — the dedicated video UI

Pulled video capabilities into their own standalone Streamlit app because
`app.py` currently hides every video tab (`SHOW_GENERATE_VIDEO` and
`SHOW_VIDEO_TRANSFORM_TABS` are both `False`), so there was no surface to
demo any of this on. Five tabs: Generate, Edit/Extend, Combine Clips,
Questions, Enhance — all backed by the real capability classes above, no
business logic duplicated in the UI layer.

Verified live through an actual browser (Playwright), not just read for
correctness: real file uploads, a real 2-clip combine producing a correct
playable result, and a real ~19-second Gemini call against an uploaded
video returning genuine content-aware questions.

---

## 8. Long-form video (topic → full video) — designed, not built

### 8.1 The real constraint

Veo's own continuous-shot ceiling is ~148 seconds (§3's Extend limit).
Gemini Omni's edit/extend can't be chained for length at all — it
hard-rejects anything over 10 seconds of input (§4.4). So **any** target
duration beyond ~2.5 minutes needs multiple separately-generated scenes,
stitched together — which is also how real instructional video is
actually produced (cuts between a new diagram, a new example), not one
unbroken take.

### 8.2 Chaining technique — tested before committing to a design

Two candidate techniques for linking scene N to scene N+1:

1. **Veo Extend, chained repeatedly.** Rejected: doesn't scale past
   ~148s/20 hops, and each additional hop operates on an ever-growing
   video rather than a fresh short generation.
2. **Last-frame conditioning.** Extract scene N's final frame (ffmpeg),
   feed it back as the *starting image* for scene N+1 — a different Veo
   input path (`GenerateVideosSource.image`) from both plain
   text-to-video (`prompt`) and Extend (`video`) — with a fresh prompt
   for what happens next. Stitch everything with `video_combine` at the
   end.

Technique 2 was untested going into this. **(Live-verified):** extracted
the last frame of an existing clip, fed it into `generate_videos()` as
the `image` source with a new prompt, on `veo-3.1-lite-generate-001`.
Result: a real 8-second clip, 1.79MB, completed in 50 seconds. Compared
the new clip's own first frame against the source clip's last frame side
by side: same subject, same pose, same background detail, same setting —
a near-exact visual match, not an approximation.

**This is the chaining technique the design uses.** No documented length
ceiling — every scene is a fresh, independent generation, so cost and
wall-clock time are the only real limits, not an API cap.

**What it does not fix:** audio does not carry across the cut. Each
scene's narration is a fresh generation — a sentence can't continue
mid-word across a scene boundary. The script-writing step has to write
each scene's narration as one complete thought that ends cleanly.

### 8.3 Proposed design — `video_long_form` (not yet built)

```
topic + target duration + audience
        |
        v
[1] SCRIPT     Gemini (text) writes a scene-by-scene breakdown sized to
               the target duration. Each scene's narration is a complete
               thought (§8.2); each visual prompt describes what changes
               from the previous frame.
        |
        v
[2] GENERATE   Scene 1: plain text-to-video. Scene 2+: extract the
               previous scene's last frame, generate again with that
               frame as the starting image + the new scene's prompt.
               Sequential (each scene genuinely depends on the last).
        |
        v
[3] COMBINE    video_combine joins every scene's clip into one final MP4.
        |
        v
   final video + the scene script (for review) + total cost
```

New `GeminiClient.generate_video()` parameter needed: `image_bytes` /
`image_mime_type`, wired to `GenerateVideosSource.image` (the path
verified in §8.2; today the method only ever sets `prompt`).

### 8.4 Cost & time — worked out before building anything

Every scene is a flat 8-second Veo generation (frame-chaining fixes
*continuity*, not *scene count*):

| Target | Scenes (@8s) | Cost (lite, $0.05/s) | Cost (standard, $0.20/s) | Wall-clock (sequential, ~40-50s/scene observed) |
|---|---|---|---|---|
| 5 min (300s) | ~38 | ~$15 | ~$60 | ~25-30 min |
| 30 min (1800s) | ~225 | ~$90 | ~$360 | ~2.5-3 hours |

### 8.5 V1 scope decisions, flagged for review before building

1. Every scene flat at 8 seconds — getting to fewer, longer scenes needs
   Extend-style chaining layered on top, which has its own ceiling
   (§3). Worth a later question, not a V1 blocker.
2. Visual continuity is now real (§8.2), not prompt-hoped-for.
3. Audio does not carry across scene boundaries — permanent, not a V1-
   vs-V2 question; the script step has to write around it.
4. Sequential generation, not parallel — a genuine dependency (each scene
   needs the previous scene's last frame), not just a concurrency-limit
   safety margin.
5. First live test should be a short target (3-4 scenes, ~24-32s), not
   the full 5 minutes, to prove the loop works before spending real time
   and money on a full run.

---

## 9. Cost summary (all video capabilities)

| Capability | Billing | Example |
|---|---|---|
| `video_generate` | Per-second Veo rate | 8-sec clip: $1.60 (standard) / $0.80 (fast) / $0.40 (lite) |
| `video_edit` (`veo_extend`) | Same per-second rate, ~7 sec added per call | ~$0.35-$1.40 per extend (lite-standard) |
| `video_edit` (`omni_edit`/`omni_extend`) | No published rate yet — reports $0/unverified | Not confirmed against an official source |
| `video_combine` | $0 — pure ffmpeg, no API call | — |
| `video_to_questions` | Token-based (gemini-2.5-flash/pro) | Live example: 4-sec video → 3 MCQs = $0.0075 (flash) / 2 MCQs = $0.0199 (pro) |
| `video_enhance` | Token-based (transcription + optional issue-flagging) | Scales with video length |

---

## 10. Sources

- [Veo 3.1 (Vertex AI docs)](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/veo/3-1-generate)
- [Extend Veo on Vertex AI-generated videos (official docs)](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/video/extend-a-veo-video)
- [Gemini Omni 1.1 Flash — docs.cloud.google.com](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/omni-1-1-flash)
- [Interactions API overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/interactions)
- [Interactions API (Gemini Developer API docs)](https://ai.google.dev/gemini-api/docs/interactions-overview)
- [Video understanding (Gemini API official docs)](https://ai.google.dev/gemini-api/docs/video-understanding)
- [Vertex AI Generative AI pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing)
- [FFmpeg Concatenate (official wiki)](https://trac.ffmpeg.org/wiki/Concatenate)
- Live API responses against this project's own Vertex AI project — the
  highest-confidence source throughout this document, cited inline as
  **(live-verified)**.
