"""Video Studio — standalone Streamlit app for every video capability.

Pulled out of the main app (app.py) into its own entry point: Veo/video-
understanding tabs are currently hidden in app.py (SHOW_GENERATE_VIDEO /
SHOW_VIDEO_TRANSFORM_TABS = False there) -- this is the dedicated surface
to demo everything video-related in one place.

Five tabs, all backed by the real capability classes under iav/capabilities/
-- no business logic duplicated here, only the UI is new:

    Generate         prompt -> new clip (Veo)
    Edit / Extend    video -> video, two mechanisms:
                       - Veo Extend: continues a clip VEO ITSELF generated
                       - Gemini Omni edit/extend: transforms or continues
                         ANY uploaded footage (not just this app's output)
    Combine Clips    several clips -> one longer file (ffmpeg)
    Questions        video -> structured comprehension questions.
                       Covers "prompt -> video -> question" too: just run
                       Generate first, download its clip, then feed that
                       file in here.
    Enhance          SME recording -> stabilised/captioned/denoised MP4

Run: streamlit run video_studio.py
"""

from __future__ import annotations

import logging
import time
import traceback
from pathlib import Path
from typing import Any

import streamlit as st

from iav.capabilities import CapabilityInput
from iav.capabilities.prompt_schema import (
    CommonAttributes,
    validate_common_attributes,
    validate_free_text,
)
from iav.capabilities.video_combine import VideoCombine
from iav.capabilities.video_edit import VideoEdit
from iav.capabilities.video_enhance import VideoEnhance
from iav.capabilities.video_generate import VideoGenerate
from iav.capabilities.video_to_questions import VideoToQuestions
from iav.models.config import load_config
from iav.storage import save_input

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("iav.video_studio")

st.set_page_config(page_title="IAV — Video Studio", layout="wide")


# ----------------------------------------------------------------------
# Shared UI primitives (self-contained copies of app.py's equivalents --
# this script runs standalone, so it does not import app.py itself)
# ----------------------------------------------------------------------


def _idx(options: list | None, value: Any) -> int:
    if not options:
        return 0
    try:
        return options.index(value)
    except ValueError:
        return 0


def _render_time_taken(seconds: float) -> None:
    st.caption(f"⏱ Time taken: {seconds:.1f}s")


def _get_inr_rate() -> float:
    return float(st.session_state.get("usd_to_inr_rate", 0.0) or 0.0)


def _render_cost(metadata: dict | None) -> None:
    """Token usage + estimated cost, shown under every result."""
    cost = (metadata or {}).get("cost")
    if not cost:
        return

    total = cost.get("total_usd", 0.0)
    calls = cost.get("calls", [])
    prompt_tok = cost.get("total_prompt_tokens", 0)
    output_tok = cost.get("total_output_tokens", 0)

    st.session_state["session_cost_usd"] = st.session_state.get("session_cost_usd", 0.0) + total

    thoughts_tok = cost.get("total_thoughts_tokens", 0)
    inr_rate = _get_inr_rate()
    label = f"Cost — est. ${total:.6f} ({prompt_tok:,} in / {output_tok:,} out tokens)"
    if thoughts_tok:
        label += f", {thoughts_tok:,} reasoning tokens"
    with st.expander(label, expanded=False):
        if cost.get("any_unverified"):
            st.warning("Some rates below are unverified (or there's no pricing entry yet) — "
                       "treat the dollar figure as a placeholder, not a bill.")
        if inr_rate:
            st.metric("Total (this result)", f"${total:.6f}", delta=f"₹{total * inr_rate:.2f}", delta_color="off")
        for call in calls:
            badge = "verified" if call.get("verified") else "⚠ unverified"
            provider = call.get("provider")
            provider_tag = f" — {provider}" if provider else ""
            st.markdown(f"**{call.get('label', call.get('model'))}** — `{call.get('model')}`{provider_tag} — {badge}")
            for note in call.get("notes", []):
                st.caption(f"ℹ {note}")
            st.divider()
        last_verified = cost.get("pricing_last_verified")
        source = cost.get("pricing_source_url")
        if last_verified or source:
            st.caption(f"Pricing last verified {last_verified or 'unknown'} — {source or 'n/a'}")


def _show_config_status() -> bool:
    with st.sidebar:
        st.markdown("### Configuration")
        try:
            cfg = load_config()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Config failed to load")
            st.error(f"Config error: {exc}")
            return False
        st.success(f"Vertex AI project: `{cfg.vertex.project_id}`")
        st.caption(f"Default location: `{cfg.vertex.location}`")
        return True


def _show_session_cost() -> None:
    with st.sidebar:
        st.divider()
        st.markdown("### Session cost (estimated)")
        st.number_input(
            "USD → INR rate (optional)", min_value=0.0,
            value=st.session_state.get("usd_to_inr_rate", 0.0), step=0.5, key="usd_to_inr_rate",
        )
        total = st.session_state.get("session_cost_usd", 0.0)
        rate = _get_inr_rate()
        st.metric("Total this session", f"${total:.6f}", delta=f"₹{total * rate:.2f}" if rate else None, delta_color="off")
        st.caption("Token counts are real; dollar amounts are estimates. See Cloud Billing for actual charges.")
        if st.button("Reset session total", key="reset-session-cost"):
            st.session_state["session_cost_usd"] = 0.0
            st.rerun()


def _common_attributes_form(key_prefix: str) -> CommonAttributes:
    outcome = st.text_input(
        "Assessment outcome (optional)",
        placeholder="e.g. Apply the Pythagorean theorem to find a missing side",
        key=f"{key_prefix}-outcome",
    )
    cols = st.columns(3)
    difficulty = cols[0].selectbox("Difficulty level", ["easy", "medium", "hard"], index=1, key=f"{key_prefix}-diff")
    audience = cols[1].selectbox(
        "Target audience", ["school", "undergraduate", "postgraduate"], index=1, key=f"{key_prefix}-aud"
    )
    qtype = cols[2].selectbox("Question type", ["mcq", "short_answer", "conceptual"], key=f"{key_prefix}-qtype")
    return CommonAttributes(
        assessment_outcome=outcome, difficulty_level=difficulty, target_audience=audience, question_type=qtype,
    )


def _show_validation_errors(errors: list[str]) -> bool:
    for err in errors:
        st.error(err)
    return not errors


def _run_and_render(label: str, fn) -> None:
    """Shared try/spinner/error-with-traceback wrapper used by every tab below."""
    try:
        with st.spinner("Working…"):
            start = time.perf_counter()
            result = fn()
            elapsed = time.perf_counter() - start
        _render_time_taken(elapsed)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s: failed", label)
        st.error(f"Failed: {exc}")
        with st.expander("Traceback"):
            st.code(traceback.format_exc())
        return None


# ----------------------------------------------------------------------
# Tab: Generate (Prompt -> Video)
# ----------------------------------------------------------------------


def _generate_tab() -> None:
    st.subheader("Generate — Prompt to Video")
    st.caption(
        "Real constraints: Veo is Preview/GA-mixed (check status per model below), clips run "
        "4–8 seconds, generation can take a few minutes, billed per second of output."
    )
    s = load_config().capability("video_generate")
    common = _common_attributes_form("gen")

    cols = st.columns(3)
    video_types = s.get("video_types") or ["Scenario Based"]
    video_type = cols[0].selectbox("Video type", video_types, key="gen-type")
    resolutions = s.get("available_resolutions") or [s.get("resolution", "720p")]
    resolution = cols[1].selectbox("Resolution", resolutions, index=_idx(resolutions, s.get("resolution")), key="gen-res")
    durations = s.get("available_durations_seconds") or [s.get("duration_seconds", 8)]
    duration = cols[2].selectbox("Length (seconds)", durations, index=_idx(durations, s.get("duration_seconds")), key="gen-dur")

    free_text = st.text_area(
        "Scenario", height=130,
        placeholder="e.g. A teacher pointing at a whiteboard, explaining a diagram of a cell",
        key="gen-freetext",
    )

    with st.expander("Advanced options", expanded=False):
        models = s.get("available_models") or [s["model"]]
        model = st.selectbox("Model", models, index=_idx(models, s["model"]), key="gen-model")
        locations = s.get("available_locations") or [s.get("location", "us-central1")]
        location = st.selectbox("Region", locations, index=_idx(locations, s.get("location")), key="gen-location")
        generate_audio = st.checkbox("Generate audio with the video", value=s.get("generate_audio", True), key="gen-audio")

    if st.button("Generate", type="primary", key="gen-go"):
        errors = validate_common_attributes(common) + validate_free_text(free_text)
        if not _show_validation_errors(errors):
            return
        result = _run_and_render(
            "Generate",
            lambda: VideoGenerate().process(CapabilityInput(
                text=free_text,
                params={
                    "assessment_outcome": common.assessment_outcome,
                    "difficulty_level": common.difficulty_level,
                    "target_audience": common.target_audience,
                    "question_type": common.question_type,
                    "video_type": video_type,
                    "model": model,
                    "location": location,
                    "resolution": resolution,
                    "duration_seconds": int(duration),
                    "generate_audio": generate_audio,
                },
            )),
        )
        if result is None:
            return
        st.success("Done.")
        st.video(str(result.file_path))
        with result.file_path.open("rb") as fh:
            st.download_button("Download MP4", data=fh.read(), file_name=result.file_path.name, mime="video/mp4", key="gen-dl")
        with st.expander("Prompt sent to the model"):
            st.text(result.text or "")
        _render_cost(result.metadata)
        st.info("Next: feed this clip into the **Questions** tab for a Prompt → Video → Question run, "
                "or into **Edit / Extend** / **Combine Clips**.")


# ----------------------------------------------------------------------
# Tab: Edit / Extend (Video -> Video)
# ----------------------------------------------------------------------


def _edit_tab() -> None:
    st.subheader("Edit / Extend — Video to Video")
    st.caption("Two genuinely different mechanisms, picked by Mode below.")

    s = load_config().capability("video_edit")
    mode = st.radio(
        "Mode",
        ["veo_extend", "omni_edit", "omni_extend"],
        format_func=lambda m: {
            "veo_extend": "Veo Extend — continue a clip Veo itself generated",
            "omni_edit": "Omni Edit — transform ANY footage per an instruction",
            "omni_extend": "Omni Extend — continue ANY footage",
        }[m],
        key="edit-mode",
    )

    if mode != "veo_extend":
        st.warning(
            "⚠ Gemini Omni is currently reachable **only** via the preview-named model on this "
            "account — the GA name (`gemini-omni-1.1-flash`, no suffix) is rejected outright. "
            "That preview model's own documented shutdown date has already passed; it's still "
            "responding as of this testing, but could stop at any time without warning. "
            "Input is also hard-capped at 10 seconds (live-verified: an 11-second clip was "
            "rejected with \"exceeds maximum duration\")."
        )

    uploaded = st.file_uploader("Upload the source video", type=["mp4", "mov", "webm", "mkv"], key="edit-upload")

    instruction = st.text_area(
        "Instruction" + (" (required for Omni modes)" if mode != "veo_extend" else " (optional — Veo Extend works without one)"),
        placeholder="e.g. Make the lighting warmer and add gentle snowfall." if mode != "veo_extend" else "",
        height=80, key="edit-instruction",
    )

    with st.expander("Advanced options", expanded=False):
        if mode == "veo_extend":
            models = s.get("available_veo_models") or [s["veo_model"]]
            model = st.selectbox("Model", models, index=_idx(models, s["veo_model"]), key="edit-veo-model")
        else:
            models = s.get("available_omni_models") or [s["omni_model"]]
            model = st.selectbox("Model", models, index=_idx(models, s["omni_model"]), key="edit-omni-model")

    if st.button("Run", type="primary", key="edit-go"):
        if uploaded is None:
            st.warning("Upload a source video first.")
            return
        if mode != "veo_extend" and not instruction.strip():
            st.warning("Omni modes need an instruction describing what to do with the footage.")
            return

        saved = save_input(uploaded.getvalue(), Path(uploaded.name).suffix or ".mp4")
        result = _run_and_render(
            "Edit/Extend",
            lambda: VideoEdit().process(CapabilityInput(
                file_path=saved, instruction=instruction, params={"mode": mode, "model": model},
            )),
        )
        if result is None:
            return
        meta = result.metadata or {}
        st.success(f"Done — {meta.get('mode')} via `{meta.get('model')}`.")
        st.video(str(result.file_path))
        with result.file_path.open("rb") as fh:
            st.download_button("Download MP4", data=fh.read(), file_name=result.file_path.name, mime="video/mp4", key="edit-dl")
        _render_cost(result.metadata)


# ----------------------------------------------------------------------
# Tab: Combine Clips
# ----------------------------------------------------------------------


def _combine_tab() -> None:
    st.subheader("Combine Clips — build a longer video")
    st.caption(
        "No single generation call here produces more than a few seconds (or ~2.5 minutes via "
        "chained Veo Extend) of continuous footage. For a real multi-topic lesson, generate each "
        "segment separately and combine them here. Order = upload order."
    )

    uploaded = st.file_uploader(
        "Upload 2 or more clips, in the order they should play",
        type=["mp4", "mov", "webm", "mkv"],
        accept_multiple_files=True,
        key="combine-upload",
    )

    if st.button("Combine", type="primary", key="combine-go"):
        if not uploaded or len(uploaded) < 2:
            st.warning("Upload at least two clips.")
            return

        saved_paths = [save_input(f.getvalue(), Path(f.name).suffix or ".mp4") for f in uploaded]
        result = _run_and_render(
            "Combine",
            lambda: VideoCombine().process(CapabilityInput(
                file_path=saved_paths[0],
                params={"clip_paths": [str(p) for p in saved_paths[1:]]},
            )),
        )
        if result is None:
            return
        meta = result.metadata or {}
        mode_label = {"stream_copy": "lossless stream-copy (clips matched)", "reencode": "re-encoded (clips differed)"}
        st.success(f"Done — combined {meta.get('input_count')} clips via {mode_label.get(meta.get('mode'), meta.get('mode'))}.")
        st.video(str(result.file_path))
        with result.file_path.open("rb") as fh:
            st.download_button("Download MP4", data=fh.read(), file_name=result.file_path.name, mime="video/mp4", key="combine-dl")
        st.caption("No Gemini call involved — pure ffmpeg, so there's no cost to show.")


# ----------------------------------------------------------------------
# Tab: Questions (Video -> Question, and Prompt -> Video -> Question)
# ----------------------------------------------------------------------


def _questions_tab() -> None:
    st.subheader("Questions — Video to Question")
    st.caption(
        "Already a real, working app capability today (unlike the Veo/Omni tabs above, which "
        "were standalone-script-only until this build). Works on any video — including one you "
        "just made in the Generate tab, which is the Prompt → Video → Question use case."
    )

    s = load_config().capability("video_to_questions")
    uploaded = st.file_uploader("Upload a video", type=["mp4", "mov", "webm", "mkv"], key="vq-upload")
    instruction = st.text_area(
        "Instruction (optional — leave blank for the default question set)",
        placeholder="Leave blank, or ask for something specific, e.g. a single short-answer question about the main concept.",
        height=80, key="vq-instruction",
    )

    with st.expander("Question settings", expanded=False):
        models = s.get("available_models") or [s["model"]]
        model = st.selectbox("Model", models, index=_idx(models, s["model"]), key="vq-model")
        cols = st.columns(3)
        count = cols[0].number_input("Number of questions", min_value=1, max_value=20, value=int(s.get("default_question_count", 5)), key="vq-count")
        qtype = cols[1].selectbox(
            "Question type", ["mcq", "short_answer", "conceptual"],
            index=_idx(["mcq", "short_answer", "conceptual"], s.get("default_question_type")), key="vq-type",
        )
        level = cols[2].selectbox(
            "Level", ["school", "undergraduate", "postgraduate"],
            index=_idx(["school", "undergraduate", "postgraduate"], s.get("default_level")), key="vq-level",
        )
        st.caption(
            f"`gemini-2.5-pro` also works here (live-verified) but isn't yet in this capability's "
            f"configured model list — add it to config.yaml's video_to_questions.available_models to offer it."
        )

    if st.button("Generate Questions", type="primary", key="vq-go"):
        if uploaded is None:
            st.warning("Upload a video first.")
            return
        saved = save_input(uploaded.getvalue(), Path(uploaded.name).suffix or ".mp4")
        result = _run_and_render(
            "Questions",
            lambda: VideoToQuestions().process(CapabilityInput(
                file_path=saved, instruction=instruction,
                params={"model": model, "count": int(count), "type": qtype, "level": level},
            )),
        )
        if result is None:
            return
        meta = result.metadata or {}
        st.success(f"Done — generated {meta.get('question_count', '?')} questions.")
        if result.text:
            st.markdown(result.text)
        if result.data:
            with st.expander("Raw JSON"):
                st.json(result.data)
        if result.file_path:
            with result.file_path.open("rb") as fh:
                st.download_button("Download JSON", data=fh.read(), file_name=result.file_path.name, mime="application/json", key="vq-dl")
        _render_cost(result.metadata)


# ----------------------------------------------------------------------
# Tab: Enhance (SME recording -> professional)
# ----------------------------------------------------------------------


def _enhance_tab() -> None:
    st.subheader("Enhance — Video to Professional")
    st.caption(
        "Upload an SME tutorial recording. Output: cleaned audio + captions + stabilisation + "
        "light colour correction. The SME's original voice is preserved — ffmpeg does the actual "
        "enhancement work; Gemini only transcribes (for captions) and optionally flags issues."
    )
    s = load_config().capability("video_enhance")
    uploaded = st.file_uploader("Upload a recording", type=["mp4", "mov", "webm", "mkv"], key="ve-upload")

    with st.expander("Pipeline options", expanded=False):
        models = s.get("available_models") or [s["analysis_model"]]
        model = st.selectbox("Analysis model", models, index=_idx(models, s["analysis_model"]), key="ve-model")
        pipeline_defaults = s.get("pipeline", {})
        cols = st.columns(5)
        stabilize = cols[0].checkbox("Stabilise", value=pipeline_defaults.get("stabilize", True), key="ve-stab")
        color = cols[1].checkbox("Colour correct", value=pipeline_defaults.get("light_color_correction", True), key="ve-color")
        denoise = cols[2].checkbox("Denoise audio", value=pipeline_defaults.get("audio_denoise", True), key="ve-denoise")
        captions = cols[3].checkbox("Auto captions", value=pipeline_defaults.get("auto_captions", True), key="ve-cap")
        flag_issues = cols[4].checkbox("Flag issues", value=pipeline_defaults.get("flag_issues", False), key="ve-flag")

    if st.button("Enhance", type="primary", key="ve-go"):
        if uploaded is None:
            st.warning("Upload a video first.")
            return
        saved = save_input(uploaded.getvalue(), Path(uploaded.name).suffix or ".mp4")
        result = _run_and_render(
            "Enhance",
            lambda: VideoEnhance().process(CapabilityInput(
                file_path=saved,
                params={
                    "model": model,
                    "pipeline": {
                        "stabilize": stabilize, "light_color_correction": color,
                        "audio_denoise": denoise, "auto_captions": captions, "flag_issues": flag_issues,
                    },
                },
            )),
        )
        if result is None:
            return
        meta = result.metadata or {}
        msg = "Done."
        if meta.get("caption_count"):
            msg += f" {meta['caption_count']} caption segments burned in."
        st.success(msg)
        st.video(str(result.file_path))
        with result.file_path.open("rb") as fh:
            st.download_button("Download MP4", data=fh.read(), file_name=result.file_path.name, mime="video/mp4", key="ve-dl")
        if meta.get("issues"):
            with st.expander("Production issues flagged by Gemini"):
                st.markdown(meta["issues"])
        if result.text:
            with st.expander("SRT captions"):
                st.code(result.text, language="text")
        _render_cost(result.metadata)


# ----------------------------------------------------------------------
# Page layout
# ----------------------------------------------------------------------

st.title("IAV — Video Studio")
st.caption(
    "Every video capability in one place — pulled out of the main app, which currently hides "
    "these tabs. Reuses the same capability classes, config, and credentials as app.py."
)

_config_ok = _show_config_status()
_show_session_cost()

if not _config_ok:
    st.stop()

tab_generate, tab_edit, tab_combine, tab_questions, tab_enhance = st.tabs(
    ["Generate", "Edit / Extend", "Combine Clips", "Questions", "Enhance"]
)

with tab_generate:
    _generate_tab()
with tab_edit:
    _edit_tab()
with tab_combine:
    _combine_tab()
with tab_questions:
    _questions_tab()
with tab_enhance:
    _enhance_tab()
