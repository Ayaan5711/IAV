"""Streamlit shell for the IAV media enhancement POC.

Two sections, each its own row of tabs:

  - Transform Existing Content: enhance/analyse SME-supplied material
  - Generate New Content: create new media from a structured, validated prompt

Every tab follows the same shape: say what you want → (optional) tune
advanced options, tucked into a collapsed expander → Process → result + cost.
The UI never references a Gemini model ID directly except as a value pulled
from config.yaml's available_* lists.
"""

from __future__ import annotations

import logging
import time
import traceback
from pathlib import Path
from typing import Any, Callable

import streamlit as st

from iav.capabilities import CapabilityInput
from iav.capabilities.audio_generate import AudioGenerate
from iav.capabilities.audio_question_generation import AudioQuestionGeneration
from iav.capabilities.audio_text_to_speech import TextToSpeech
from iav.capabilities.audio_to_audio import AudioToAudio
from iav.capabilities.image_enhance import ImageEnhance
from iav.capabilities.image_generate import ImageGenerate
from iav.capabilities.prompt_schema import CommonAttributes, validate_common_attributes, validate_free_text
from iav.capabilities.video_enhance import VideoEnhance
from iav.capabilities.video_generate import VideoGenerate
from iav.capabilities.video_to_questions import VideoToQuestions
from iav.models.config import load_config
from iav.storage import save_input

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("iav.app")


st.set_page_config(
    page_title="IAV — Gemini Media Enhancement",
    layout="wide",
)

# Veo generation is hidden for now (Preview-only, narrow regional
# availability, multi-minute latency) -- capability code stays intact
# for when it's ready to demo.
SHOW_GENERATE_VIDEO = False


# ----------------------------------------------------------------------
# Shared UI primitives
# ----------------------------------------------------------------------


def _idx(options: list | None, value: Any) -> int:
    if not options:
        return 0
    try:
        return options.index(value)
    except ValueError:
        return 0


def _show_config_status() -> bool:
    """Render auth/config status in the sidebar. Returns True if ready."""
    with st.sidebar:
        st.markdown("### Configuration")
        try:
            cfg = load_config()
        except Exception as exc:  # noqa: BLE001 — we want to surface any config error
            logger.exception("Config failed to load")
            st.error(f"Config error: {exc}")
            return False

        st.success(f"Vertex AI project: `{cfg.vertex.project_id}`")
        st.caption(f"Location: `{cfg.vertex.location}`")
        return True


def _get_inr_rate() -> float:
    return float(st.session_state.get("usd_to_inr_rate", 0.0) or 0.0)


def _show_session_cost() -> None:
    with st.sidebar:
        st.divider()
        st.markdown("### Session cost (estimated)")
        st.number_input(
            "USD → INR rate (optional)",
            min_value=0.0,
            value=st.session_state.get("usd_to_inr_rate", 0.0),
            step=0.5,
            key="usd_to_inr_rate",
            help="Enter today's rate to also show costs converted to INR. Leave at 0 to show USD only.",
        )
        total = st.session_state.get("session_cost_usd", 0.0)
        rate = _get_inr_rate()
        st.metric("Total this session", f"${total:.6f}" + (f" (₹{total * rate:.2f})" if rate else ""))
        st.caption("Token counts are real; dollar amounts are estimates. See Cloud Billing for actual charges.")
        if st.button("Reset session total", key="reset-session-cost"):
            st.session_state["session_cost_usd"] = 0.0
            st.rerun()


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

    if calls and prompt_tok == 0 and output_tok == 0:
        st.caption("⚠ No usage data returned by the API — cost could not be estimated for this call.")

    thoughts_tok = cost.get("total_thoughts_tokens", 0)
    inr_rate = _get_inr_rate()
    inr_suffix = f" (₹{total * inr_rate:.2f})" if inr_rate else ""
    label = f"Cost — est. ${total:.6f}{inr_suffix} ({prompt_tok:,} in / {output_tok:,} out tokens)"
    if thoughts_tok:
        label += f", {thoughts_tok:,} reasoning tokens"
    with st.expander(label, expanded=False):
        if cost.get("any_unverified"):
            st.warning("Some rates below are unverified against an official Google source.")
        if inr_rate:
            st.caption(f"Converted at ₹{inr_rate:.2f} / $1 (rate entered manually in the sidebar).")
        for call in calls:
            badge = "verified" if call.get("verified") else "⚠ unverified"
            st.markdown(f"**{call.get('label', call.get('model'))}** — `{call.get('model')}` — {badge}")
            tok = call.get("tokens", {})
            input_usd = call.get("input_usd", 0.0)
            output_usd = call.get("output_usd", 0.0)
            cols = st.columns(4)
            cols[0].metric("Input tokens", f"{tok.get('prompt', 0):,}")
            cols[1].metric("Output tokens", f"{tok.get('output', 0):,}")
            cols[2].metric("Input cost", f"${input_usd:.6f}" + (f" / ₹{input_usd * inr_rate:.2f}" if inr_rate else ""))
            cols[3].metric("Output cost", f"${output_usd:.6f}" + (f" / ₹{output_usd * inr_rate:.2f}" if inr_rate else ""))
            if tok.get("thoughts") or tok.get("tool_use") or tok.get("cached"):
                extras = []
                if tok.get("thoughts"):
                    extras.append(f"{tok['thoughts']:,} reasoning tokens (billed with output)")
                if tok.get("tool_use"):
                    extras.append(f"{tok['tool_use']:,} tool-use tokens (billed with input)")
                if tok.get("cached"):
                    extras.append(f"{tok['cached']:,} cached tokens")
                st.caption("Also: " + " · ".join(extras))
            for note in call.get("notes", []):
                st.caption(f"ℹ {note}")
            st.divider()
        last_verified = cost.get("pricing_last_verified")
        source = cost.get("pricing_source_url")
        if last_verified or source:
            st.caption(f"Pricing last verified {last_verified or 'unknown'} — {source or 'n/a'}")


def _render_time_taken(seconds: float) -> None:
    st.caption(f"⏱ Time taken: {seconds:.1f}s")


def _capability_tab(
    *,
    title: str,
    description: str,
    accept_types: list[str] | None,
    default_instruction: str,
    run: Callable[[Any, str, dict], object],
    output_renderer: Callable[[object], None],
    options_renderer: Callable[[], dict] | None = None,
    options_label: str = "Advanced options",
) -> None:
    """Generic tab: input → instruction → advanced options → process → result.

    Technical dials (model, voice, resolution, pipeline toggles) live inside
    a collapsed expander so the default view is just "say what you want and
    go" — the same shape for every tab, options tucked away until wanted.
    """
    st.subheader(title)
    st.caption(description)

    if accept_types is None:
        uploaded = None
        text_input = st.text_area(
            "Input text",
            height=180,
            placeholder="Paste the script here…",
            key=f"text-{title}",
        )
    else:
        uploaded = st.file_uploader(
            "Upload file",
            type=accept_types,
            key=f"upload-{title}",
        )
        text_input = None

    instruction = st.text_area(
        "Instruction (optional — leave blank to use the default)",
        value="",
        placeholder=default_instruction,
        height=100,
        key=f"instruction-{title}",
    )

    if options_renderer:
        with st.expander(options_label, expanded=False):
            params = options_renderer()
    else:
        params = {}

    if st.button("Process", type="primary", key=f"go-{title}"):
        if accept_types is not None and uploaded is None:
            st.warning("Upload a file first.")
            return
        if accept_types is None and not (text_input or "").strip():
            st.warning("Enter some text first.")
            return

        logger.info("Tab '%s': Process clicked", title)
        try:
            with st.spinner("Working…"):
                start = time.perf_counter()
                if accept_types is not None:
                    suffix = Path(uploaded.name).suffix or ""
                    saved = save_input(uploaded.getvalue(), suffix)
                    result = run(saved, instruction, params)
                else:
                    result = run(text_input, instruction, params)
                elapsed = time.perf_counter() - start
            _render_time_taken(elapsed)
            output_renderer(result)
        except NotImplementedError as exc:
            logger.warning("Tab '%s': not yet implemented: %s", title, exc)
            st.info(f"Not yet implemented: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Tab '%s': Process failed", title)
            st.error(f"Failed: {exc}")
            with st.expander("Traceback"):
                st.code(traceback.format_exc())


def _common_attributes_form(key_prefix: str) -> CommonAttributes:
    """The four assessment-metadata fields shared by every generate tab."""
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
    qtype = cols[2].selectbox(
        "Question type", ["mcq", "short_answer", "conceptual"], key=f"{key_prefix}-qtype"
    )
    return CommonAttributes(
        assessment_outcome=outcome,
        difficulty_level=difficulty,
        target_audience=audience,
        question_type=qtype,
    )


def _show_validation_errors(errors: list[str]) -> bool:
    """Renders validation errors. Returns True if there were none (i.e. valid)."""
    for err in errors:
        st.error(err)
    return not errors


# ----------------------------------------------------------------------
# Transform Existing Content — enhance/analyse SME-supplied material
# ----------------------------------------------------------------------


def _image_enhance_options() -> dict:
    s = load_config().capability("image_enhance")
    cols = st.columns(2)
    models = s.get("available_models") or [s["model"]]
    model = cols[0].selectbox("Model", models, index=_idx(models, s["model"]), key="ie-model")
    resolutions = s.get("available_resolutions") or [s.get("resolution", "2K")]
    resolution = cols[1].selectbox(
        "Resolution", resolutions, index=_idx(resolutions, s.get("resolution")), key="ie-res"
    )
    return {"model": model, "resolution": resolution}


def _run_image(saved: Path, instruction: str, params: dict):
    cap = ImageEnhance()
    return cap.process(CapabilityInput(file_path=saved, instruction=instruction, params=params))


def _render_image_output(result) -> None:  # type: ignore[no-untyped-def]
    out_path: Path = result.file_path
    st.success("Done.")
    st.image(str(out_path), caption=out_path.name)
    with out_path.open("rb") as fh:
        st.download_button(
            "Download",
            data=fh.read(),
            file_name=out_path.name,
            mime=result.metadata.get("mime_type", "image/png"),
        )
    _render_cost(result.metadata)


def _tts_options() -> dict:
    s = load_config().capability("audio_text_to_speech")
    cols = st.columns(2)
    models = s.get("available_models") or [s["model"]]
    model = cols[0].selectbox("Model", models, index=_idx(models, s["model"]), key="tts-model")
    voices = s.get("available_voices") or [s.get("voice_preset", "Kore")]
    voice = cols[1].selectbox("Voice", voices, index=_idx(voices, s.get("voice_preset")), key="tts-voice")
    return {"model": model, "voice": voice}


def _run_text_to_speech(text: str, instruction: str, params: dict):
    cap = TextToSpeech()
    return cap.process(CapabilityInput(text=text, instruction=instruction, params=params))


def _render_audio_output(result) -> None:  # type: ignore[no-untyped-def]
    st.success("Done.")
    if result.file_path:
        st.audio(str(result.file_path))
        mime = (result.metadata or {}).get("mime_type", "audio/wav")
        with result.file_path.open("rb") as fh:
            st.download_button(
                "Download",
                data=fh.read(),
                file_name=result.file_path.name,
                mime=mime,
            )
    _render_cost(result.metadata)


def _video_questions_options() -> dict:
    s = load_config().capability("video_to_questions")
    models = s.get("available_models") or [s["model"]]
    model = st.selectbox("Model", models, index=_idx(models, s["model"]), key="vq-model")
    cols = st.columns(3)
    count = cols[0].number_input(
        "Number of questions", min_value=1, max_value=20, value=int(s.get("default_question_count", 5)), key="vq-count"
    )
    qtype = cols[1].selectbox(
        "Question type", ["mcq", "short_answer", "conceptual"],
        index=_idx(["mcq", "short_answer", "conceptual"], s.get("default_question_type")), key="vq-type",
    )
    level = cols[2].selectbox(
        "Level", ["school", "undergraduate", "postgraduate"],
        index=_idx(["school", "undergraduate", "postgraduate"], s.get("default_level")), key="vq-level",
    )
    return {"model": model, "count": int(count), "type": qtype, "level": level}


def _run_video_questions(saved: Path, instruction: str, params: dict):
    cap = VideoToQuestions()
    return cap.process(CapabilityInput(file_path=saved, instruction=instruction, params=params))


def _render_questions_output(result) -> None:  # type: ignore[no-untyped-def]
    meta = result.metadata or {}
    st.success(f"Done — generated {meta.get('question_count', '?')} questions.")
    if result.text:
        st.markdown(result.text)
    if result.data:
        with st.expander("Raw JSON"):
            st.json(result.data)
    if result.file_path:
        with result.file_path.open("rb") as fh:
            st.download_button(
                "Download JSON",
                data=fh.read(),
                file_name=result.file_path.name,
                mime="application/json",
            )
    _render_cost(result.metadata)


def _video_enhance_options() -> dict:
    s = load_config().capability("video_enhance")
    models = s.get("available_models") or [s["analysis_model"]]
    model = st.selectbox("Analysis model", models, index=_idx(models, s["analysis_model"]), key="ve-model")

    st.caption("Pipeline steps")
    pipeline_defaults = s.get("pipeline", {})
    cols = st.columns(5)
    stabilize = cols[0].checkbox("Stabilise", value=pipeline_defaults.get("stabilize", True), key="ve-stab")
    color = cols[1].checkbox("Colour correct", value=pipeline_defaults.get("light_color_correction", True), key="ve-color")
    denoise = cols[2].checkbox("Denoise audio", value=pipeline_defaults.get("audio_denoise", True), key="ve-denoise")
    captions = cols[3].checkbox("Auto captions", value=pipeline_defaults.get("auto_captions", True), key="ve-cap")
    flag_issues = cols[4].checkbox("Flag issues", value=pipeline_defaults.get("flag_issues", False), key="ve-flag")

    encoder_defaults = s.get("encoder", {})
    presets = encoder_defaults.get("available_presets") or [encoder_defaults.get("preset", "medium")]
    preset = st.selectbox(
        "Encoder preset (speed vs. quality)", presets, index=_idx(presets, encoder_defaults.get("preset")), key="ve-preset"
    )

    return {
        "model": model,
        "pipeline": {
            "stabilize": stabilize,
            "light_color_correction": color,
            "audio_denoise": denoise,
            "auto_captions": captions,
            "flag_issues": flag_issues,
        },
        "encoder": {"preset": preset},
    }


def _run_video_enhance(saved: Path, instruction: str, params: dict):
    cap = VideoEnhance()
    return cap.process(CapabilityInput(file_path=saved, instruction=instruction, params=params))


def _render_video_output(result) -> None:  # type: ignore[no-untyped-def]
    meta = result.metadata or {}
    msg_parts = ["Done."]
    if meta.get("caption_count"):
        msg_parts.append(f"{meta['caption_count']} caption segments burned in.")
    st.success(" ".join(msg_parts))
    if result.file_path:
        st.video(str(result.file_path))
        with result.file_path.open("rb") as fh:
            st.download_button(
                "Download MP4",
                data=fh.read(),
                file_name=result.file_path.name,
                mime="video/mp4",
            )
    if meta.get("issues"):
        with st.expander("Production issues flagged by Gemini"):
            st.markdown(meta["issues"])
    if result.text:
        with st.expander("SRT captions"):
            st.code(result.text, language="text")
    _render_cost(result.metadata)


def _audio_to_audio_tab() -> None:
    """Recording -> transcript -> re-narrated audio, or a topic -> narration.

    Either way, ends with comprehension questions generated from the script.
    """
    st.subheader("Audio → Audio")
    st.caption(
        "Upload a recording (transcribed via Azure Speech, multilingual incl. Indian "
        "languages, falling back to Gemini if Azure isn't configured), or skip straight "
        "to a topic/scenario. Either way: re-narrated audio plus comprehension questions."
    )

    s = load_config().capability("audio_to_audio")
    az = load_config().azure_speech

    mode_label = st.radio(
        "Input type",
        ["Upload recording", "Topic / Scenario"],
        key="a2a-mode",
        horizontal=True,
    )
    mode = "upload" if mode_label.startswith("Upload") else "topic"

    uploaded = None
    free_text = None
    language = None
    length = None

    if mode == "upload":
        uploaded = st.file_uploader(
            "Upload file", type=["mp3", "wav", "m4a", "ogg", "flac"], key="a2a-upload"
        )
        languages = az.get("available_languages") or ["en-US"]
        language = st.selectbox(
            "Spoken language", languages, index=_idx(languages, az.get("default_language")), key="a2a-lang"
        )
    else:
        free_text = st.text_area(
            "Topic / scenario",
            height=130,
            placeholder="e.g. Explain how a diode works in a simple circuit",
            key="a2a-freetext",
        )
        lengths = s.get("lengths") or ["Short (~30s)"]
        length = st.selectbox("Length", lengths, key="a2a-length")

    cols = st.columns(3)
    count = cols[0].number_input(
        "Number of questions", min_value=1, max_value=20, value=int(s.get("default_question_count", 5)), key="a2a-count"
    )
    qtype = cols[1].selectbox("Question type", ["mcq", "short_answer", "conceptual"], key="a2a-qtype")
    level = cols[2].selectbox(
        "Level", ["school", "undergraduate", "postgraduate"], index=1, key="a2a-level"
    )

    with st.expander("Advanced options", expanded=False):
        cols2 = st.columns(2)
        text_models = s.get("available_text_models") or [s["question_model"]]
        question_model = cols2[0].selectbox(
            "Question / cleanup model", text_models, index=_idx(text_models, s["question_model"]), key="a2a-qmodel"
        )
        tts_models = s.get("available_tts_models") or [s["tts_model"]]
        tts_model = cols2[1].selectbox("TTS model", tts_models, index=_idx(tts_models, s["tts_model"]), key="a2a-ttsmodel")
        voices = s.get("available_voices") or [s.get("voice_preset", "Kore")]
        voice = st.selectbox("Voice", voices, index=_idx(voices, s.get("voice_preset")), key="a2a-voice")

    if st.button("Process", type="primary", key="a2a-go"):
        if mode == "upload" and uploaded is None:
            st.warning("Upload a file first.")
            return
        if mode == "topic" and not (free_text or "").strip():
            st.warning("Enter a topic or scenario first.")
            return

        logger.info("Audio -> Audio: Process clicked (mode=%s)", mode)
        try:
            with st.spinner("Working…"):
                start = time.perf_counter()
                cap = AudioToAudio()
                base_params = {
                    "mode": mode,
                    "question_model": question_model,
                    "tts_model": tts_model,
                    "voice": voice,
                    "count": int(count),
                    "type": qtype,
                    "level": level,
                }
                if mode == "upload":
                    suffix = Path(uploaded.name).suffix or ""
                    saved = save_input(uploaded.getvalue(), suffix)
                    result = cap.process(
                        CapabilityInput(file_path=saved, params={**base_params, "language": language})
                    )
                else:
                    result = cap.process(
                        CapabilityInput(text=free_text, params={**base_params, "length": length})
                    )
                elapsed = time.perf_counter() - start
            _render_time_taken(elapsed)
            _render_audio_to_audio_output(result)
        except NotImplementedError as exc:
            logger.warning("Audio -> Audio: not yet implemented: %s", exc)
            st.info(f"Not yet implemented: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Audio -> Audio: Process failed")
            st.error(f"Failed: {exc}")
            with st.expander("Traceback"):
                st.code(traceback.format_exc())


def _render_audio_to_audio_output(result) -> None:  # type: ignore[no-untyped-def]
    meta = result.metadata or {}
    st.success("Done.")
    if meta.get("duration_seconds"):
        st.metric("Audio duration", f"{meta['duration_seconds']:.1f}s")
    if result.file_path:
        st.audio(str(result.file_path))
        with result.file_path.open("rb") as fh:
            st.download_button(
                "Download audio",
                data=fh.read(),
                file_name=result.file_path.name,
                mime=meta.get("mime_type", "audio/wav"),
            )
    if meta.get("asr_engine"):
        st.caption(f"Transcribed via: {meta['asr_engine']}")
        if "fallback" in meta["asr_engine"]:
            st.caption("ℹ Azure Speech was unavailable for this run — used the Gemini ASR fallback.")
    if meta.get("raw_transcript"):
        with st.expander("Transcript"):
            st.text(meta["raw_transcript"])
        if meta.get("cleaned_script") and meta["cleaned_script"] != meta["raw_transcript"]:
            with st.expander("Script used for narration"):
                st.text(meta["cleaned_script"])
    elif result.text:
        with st.expander("Script used for narration"):
            st.text(result.text)
    if result.data:
        with st.expander(f"Questions ({meta.get('question_count', '?')})"):
            st.json(result.data)
        q_path = meta.get("questions_json_path")
        if q_path and Path(q_path).exists():
            with Path(q_path).open("rb") as fh:
                st.download_button(
                    "Download questions JSON", data=fh.read(), file_name=Path(q_path).name, mime="application/json"
                )
    if meta.get("asr_engine", "").startswith("Azure"):
        st.caption("ℹ Azure Speech transcription is billed separately by Azure — not included in the cost estimate below.")
    _render_cost(meta)


def _audio_questions_tab() -> None:
    """Topic/scenario/passage -> narrated audio + text comprehension questions."""
    st.subheader("Audio → Questions")
    st.caption(
        "Give a topic/scenario and Gemini writes a passage, or paste your own passage/script. "
        "Either way: narrated audio plus text comprehension questions with an answer key."
    )

    s = load_config().capability("audio_question_generation")

    mode_label = st.radio(
        "Input type",
        ["Topic / Scenario (Gemini writes the passage)", "My own passage/script"],
        key="aq-mode",
        horizontal=True,
    )
    mode = "topic" if mode_label.startswith("Topic") else "passage"

    text_input = st.text_area(
        "Topic / scenario" if mode == "topic" else "Passage / script",
        height=140,
        placeholder=(
            "e.g. Photosynthesis, or a scenario like 'A plant growing towards a window'"
            if mode == "topic" else "Paste the full passage or script text here…"
        ),
        key="aq-text",
    )

    cols = st.columns(2)
    speaker_mode = cols[0].selectbox("Speakers", s["speaker_modes"], key="aq-speakers")
    multi_speaker = speaker_mode == "Multiple speakers"
    lengths = s.get("lengths") or ["Short (~30s)"]
    length = cols[1].selectbox("Length", lengths, key="aq-length", disabled=(mode == "passage"))

    cols2 = st.columns(3)
    count = cols2[0].number_input("Number of questions", min_value=1, max_value=20, value=5, key="aq-count")
    qtype = cols2[1].selectbox("Question type", ["mcq", "short_answer", "conceptual"], key="aq-type")
    level = cols2[2].selectbox("Level", ["school", "undergraduate", "postgraduate"], index=1, key="aq-level")

    with st.expander("Advanced options", expanded=False):
        cols3 = st.columns(2)
        text_models = s.get("available_text_models") or [s["text_model"]]
        text_model = cols3[0].selectbox("Text model", text_models, index=_idx(text_models, s["text_model"]), key="aq-textmodel")
        voices = s.get("available_voices") or [s.get("voice_preset", "Kore")]
        voice = cols3[1].selectbox(
            "Voice (single-speaker only)", voices, index=_idx(voices, s.get("voice_preset")),
            key="aq-voice", disabled=multi_speaker,
        )
        cols4 = st.columns(2)
        accents = s.get("accents") or ["Neutral"]
        accent = cols4[0].selectbox("Accent", accents, key="aq-accent")
        speeds = s.get("speeds") or ["Normal"]
        speed = cols4[1].selectbox("Speed", speeds, key="aq-speed")
        tones = s.get("tones") or ["Neutral"]
        tone = st.selectbox("Tone", tones, key="aq-tone")
        instruction = st.text_area(
            "Narration instruction (optional — leave blank to use the default)",
            value="",
            height=80,
            key="aq-instruction",
        )

    if st.button("Process", type="primary", key="aq-go"):
        if not (text_input or "").strip():
            st.warning("Enter a topic/scenario or a passage first.")
            return
        logger.info("Audio -> Questions: Process clicked (mode=%s)", mode)
        try:
            with st.spinner("Working…"):
                start = time.perf_counter()
                cap = AudioQuestionGeneration()
                result = cap.process(
                    CapabilityInput(
                        text=text_input,
                        instruction=instruction,
                        params={
                            "mode": mode,
                            "count": int(count),
                            "type": qtype,
                            "level": level,
                            "text_model": text_model,
                            "voice": voice,
                            "multi_speaker": multi_speaker,
                            "accent": accent,
                            "speed": speed,
                            "tone": tone,
                            "length": length,
                        },
                    )
                )
                elapsed = time.perf_counter() - start
            _render_time_taken(elapsed)
            _render_audio_questions_output(result)
        except NotImplementedError as exc:
            logger.warning("Audio -> Questions: not yet implemented: %s", exc)
            st.info(f"Not yet implemented: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Audio -> Questions: Process failed")
            st.error(f"Failed: {exc}")
            with st.expander("Traceback"):
                st.code(traceback.format_exc())


def _render_audio_questions_output(result) -> None:  # type: ignore[no-untyped-def]
    meta = result.metadata or {}
    st.success(f"Done — generated {meta.get('question_count', '?')} questions.")
    if meta.get("duration_seconds"):
        st.metric("Audio duration", f"{meta['duration_seconds']:.1f}s")
    if meta.get("mode") == "topic" and meta.get("passage"):
        with st.expander("Generated passage"):
            st.write(meta["passage"])
    if result.file_path:
        st.audio(str(result.file_path))
        with result.file_path.open("rb") as fh:
            st.download_button(
                "Download audio",
                data=fh.read(),
                file_name=result.file_path.name,
                mime="audio/wav",
            )
    if result.text:
        st.markdown(result.text)
    if result.data:
        with st.expander("Raw questions JSON"):
            st.json(result.data)
    _render_cost(meta)


# ----------------------------------------------------------------------
# Generate New Content — new media from a structured, validated prompt
# ----------------------------------------------------------------------


def _generate_image_tab() -> None:
    st.subheader("Generate Image")
    st.caption("No sketch needed — describe what's wanted and Gemini generates it from scratch.")

    s = load_config().capability("image_generate")
    common = _common_attributes_form("gi")

    cols = st.columns(2)
    visual_type = cols[0].selectbox("Visual type", s["visual_types"], key="gi-visual")
    style = cols[1].selectbox("Style", s["styles"], key="gi-style")

    free_text = st.text_area(
        "Describe the image",
        height=110,
        placeholder="e.g. A right triangle with legs 3 and 4, hypotenuse labelled c",
        key="gi-freetext",
    )

    with st.expander("Advanced options", expanded=False):
        cols2 = st.columns(3)
        models = s.get("available_models") or [s["model"]]
        model = cols2[0].selectbox("Model", models, index=_idx(models, s["model"]), key="gi-model")
        resolutions = s.get("available_resolutions") or [s.get("resolution", "2K")]
        resolution = cols2[1].selectbox("Resolution", resolutions, index=_idx(resolutions, s.get("resolution")), key="gi-res")
        formats = s.get("available_formats") or [s.get("output_format", "png")]
        output_format = cols2[2].selectbox("Output format", formats, index=_idx(formats, s.get("output_format")), key="gi-fmt")

    if st.button("Generate", type="primary", key="gi-go"):
        errors = validate_common_attributes(common) + validate_free_text(free_text)
        if not _show_validation_errors(errors):
            return
        logger.info("Generate Image: clicked (visual_type=%s, style=%s)", visual_type, style)
        try:
            with st.spinner("Generating…"):
                start = time.perf_counter()
                cap = ImageGenerate()
                result = cap.process(
                    CapabilityInput(
                        text=free_text,
                        params={
                            "assessment_outcome": common.assessment_outcome,
                            "difficulty_level": common.difficulty_level,
                            "target_audience": common.target_audience,
                            "question_type": common.question_type,
                            "visual_type": visual_type,
                            "style": style,
                            "model": model,
                            "resolution": resolution,
                            "output_format": output_format,
                        },
                    )
                )
                elapsed = time.perf_counter() - start
            st.success("Done.")
            _render_time_taken(elapsed)
            st.image(str(result.file_path), caption=result.file_path.name)
            with result.file_path.open("rb") as fh:
                st.download_button(
                    "Download", data=fh.read(), file_name=result.file_path.name,
                    mime=result.metadata.get("mime_type", "image/png"),
                )
            with st.expander("Prompt sent to Gemini"):
                st.text(result.metadata.get("prompt", ""))
            _render_cost(result.metadata)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Generate Image: failed")
            st.error(f"Failed: {exc}")
            with st.expander("Traceback"):
                st.code(traceback.format_exc())


def _generate_audio_tab() -> None:
    st.subheader("Generate Audio")
    st.caption("No recording needed — describe the content and delivery, Gemini narrates it from scratch.")

    s = load_config().capability("audio_generate")
    common = _common_attributes_form("ga")

    mode_label = st.radio(
        "Input type",
        ["Topic (Gemini writes the narration)", "My own script (narrated verbatim)"],
        key="ga-mode",
        horizontal=True,
    )
    mode = "topic" if mode_label.startswith("Topic") else "script"

    cols = st.columns(2)
    speaker_mode = cols[0].selectbox("Speakers", s["speaker_modes"], key="ga-speakers")
    multi_speaker = speaker_mode == "Multiple speakers"
    accent = cols[1].selectbox("Accent", s["accents"], key="ga-accent")

    cols2 = st.columns(2)
    speed = cols2[0].selectbox("Speed", s["speeds"], key="ga-speed")
    tone = cols2[1].selectbox("Tone", s["tones"], key="ga-tone")

    length = st.selectbox("Length", s["lengths"], key="ga-length")

    free_text = st.text_area(
        "Topic / brief" if mode == "topic" else "Script (narrated exactly as written)",
        height=130,
        placeholder=(
            "e.g. Explain the water cycle in three stages: evaporation, condensation, precipitation."
            if mode == "topic"
            else "Paste the exact final script here…"
        ),
        key="ga-freetext",
    )

    with st.expander("Advanced options", expanded=False):
        cols3 = st.columns(2)
        text_models = s.get("available_text_models") or [s.get("text_model", s["model"])]
        text_model = cols3[0].selectbox(
            "Narration writer model", text_models, index=_idx(text_models, s.get("text_model")),
            key="ga-textmodel", disabled=(mode == "script"),
        )
        models = s.get("available_models") or [s["model"]]
        model = cols3[1].selectbox("TTS model", models, index=_idx(models, s["model"]), key="ga-model")

        cols4 = st.columns(2)
        voices = s.get("available_voices") or [s.get("voice_preset", "Kore")]
        voice = cols4[0].selectbox(
            "Voice (single-speaker only)", voices, index=_idx(voices, s.get("voice_preset")),
            key="ga-voice", disabled=multi_speaker,
        )
        formats = s.get("available_formats") or [s.get("output_format", "wav")]
        output_format = cols4[1].selectbox(
            "Output format", formats, index=_idx(formats, s.get("output_format")), key="ga-fmt"
        )

    if st.button("Generate", type="primary", key="ga-go"):
        errors = validate_common_attributes(common) + validate_free_text(free_text)
        if not _show_validation_errors(errors):
            return
        logger.info("Generate Audio: clicked (mode=%s, multi_speaker=%s, accent=%s)", mode, multi_speaker, accent)
        try:
            with st.spinner("Generating…"):
                start = time.perf_counter()
                cap = AudioGenerate()
                result = cap.process(
                    CapabilityInput(
                        text=free_text,
                        params={
                            "mode": mode,
                            "assessment_outcome": common.assessment_outcome,
                            "difficulty_level": common.difficulty_level,
                            "target_audience": common.target_audience,
                            "question_type": common.question_type,
                            "multi_speaker": multi_speaker,
                            "accent": accent,
                            "speed": speed,
                            "tone": tone,
                            "length": length,
                            "model": model,
                            "text_model": text_model,
                            "voice": voice,
                            "output_format": output_format,
                        },
                    )
                )
                elapsed = time.perf_counter() - start
            st.success("Done.")
            _render_time_taken(elapsed)
            st.audio(str(result.file_path))
            with result.file_path.open("rb") as fh:
                st.download_button(
                    "Download", data=fh.read(), file_name=result.file_path.name,
                    mime=result.metadata.get("mime_type", "audio/wav"),
                )
            if result.metadata.get("format_note"):
                st.caption(f"ℹ {result.metadata['format_note']}")
            if result.metadata.get("mode") == "topic":
                with st.expander("Narration script Gemini wrote"):
                    st.write(result.metadata.get("narration_content", ""))
            with st.expander("Full prompt sent to TTS"):
                st.text(result.text or "")
            _render_cost(result.metadata)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Generate Audio: failed")
            st.error(f"Failed: {exc}")
            with st.expander("Traceback"):
                st.code(traceback.format_exc())


def _generate_video_tab() -> None:
    st.subheader("Generate Video")
    st.caption(
        "Real constraints: Preview-only model, 4-8 second clips, generation can take several minutes, "
        "billed per second of output. This produces one short clip, not a full scenario film."
    )

    s = load_config().capability("video_generate")
    common = _common_attributes_form("gv")

    cols = st.columns(3)
    video_types = s.get("video_types") or ["Scenario Based"]
    video_type = cols[0].selectbox("Video type", video_types, key="gv-type")
    resolutions = s.get("available_resolutions") or [s.get("resolution", "720p")]
    resolution = cols[1].selectbox("Resolution", resolutions, index=_idx(resolutions, s.get("resolution")), key="gv-res")
    durations = s.get("available_durations_seconds") or [s.get("duration_seconds", 8)]
    duration = cols[2].selectbox(
        "Length (seconds)", durations, index=_idx(durations, s.get("duration_seconds")), key="gv-dur"
    )

    free_text = st.text_area(
        "Scenario",
        height=130,
        placeholder="e.g. A student measuring the angle of a ramp with a protractor in a physics lab",
        key="gv-freetext",
    )

    with st.expander("Advanced options", expanded=False):
        models = s.get("available_models") or [s["model"]]
        model = st.selectbox("Model", models, index=_idx(models, s["model"]), key="gv-model")
        locations = s.get("available_locations") or [s.get("location", "us-central1")]
        location = st.selectbox(
            "Region", locations, index=_idx(locations, s.get("location")), key="gv-location",
            help="Veo has narrower regional availability than other Gemini models. If generation 404s, try a different region here.",
        )
        generate_audio = st.checkbox("Generate audio with the video", value=s.get("generate_audio", True), key="gv-audio")

    if st.button("Generate", type="primary", key="gv-go"):
        errors = validate_common_attributes(common) + validate_free_text(free_text)
        if not _show_validation_errors(errors):
            return
        logger.info(
            "Generate Video: clicked (video_type=%s, resolution=%s, duration=%ds)",
            video_type, resolution, duration,
        )
        try:
            with st.spinner(f"Generating video — this can take a few minutes (Veo, up to {int(s.get('poll_timeout_seconds', 360))}s)…"):
                start = time.perf_counter()
                cap = VideoGenerate()
                result = cap.process(
                    CapabilityInput(
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
                    )
                )
                elapsed = time.perf_counter() - start
            st.success("Done.")
            _render_time_taken(elapsed)
            st.video(str(result.file_path))
            with result.file_path.open("rb") as fh:
                st.download_button(
                    "Download MP4", data=fh.read(), file_name=result.file_path.name, mime="video/mp4"
                )
            with st.expander("Prompt sent to Veo"):
                st.text(result.text or "")
            _render_cost(result.metadata)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Generate Video: failed")
            st.error(f"Failed: {exc}")
            with st.expander("Traceback"):
                st.code(traceback.format_exc())


# ----------------------------------------------------------------------
# Page layout
# ----------------------------------------------------------------------


st.title("IAV — Gemini Media Enhancement")
st.caption("POC for SME content authoring. Built on Vertex AI.")

_config_ok = _show_config_status()
_show_session_cost()

st.header("Transform Existing Content")
st.caption("Enhance or analyse material the SME already produced — a sketch, a recording, a video.")

transform_tabs = st.tabs([
    "Image",
    "Text → Audio",
    "Audio → Audio",
    "Video → Questions",
    "Video → Professional",
    "Audio → Questions",
])

with transform_tabs[0]:
    _capability_tab(
        title="Image — hand-drawn diagram → professional render",
        description=(
            "Upload an SME's hand-drawn diagram. Labels, numbers, and "
            "geometric relationships are preserved exactly."
        ),
        accept_types=["png", "jpg", "jpeg", "webp"],
        default_instruction=(
            "Re-render this hand-drawn diagram as a clean, professional "
            "illustration. Preserve every label, number, and geometric "
            "relationship exactly."
        ),
        run=_run_image,
        output_renderer=_render_image_output,
        options_renderer=_image_enhance_options,
        options_label="Model & resolution",
    )

with transform_tabs[1]:
    _capability_tab(
        title="Text → Audio",
        description="Paste a script. Get studio-quality narration in the chosen voice preset.",
        accept_types=None,
        default_instruction=(
            "Read clearly and at a measured, neutral pace, suitable for a "
            "listen-and-repeat English assessment."
        ),
        run=_run_text_to_speech,
        output_renderer=_render_audio_output,
        options_renderer=_tts_options,
        options_label="Model & voice",
    )

with transform_tabs[2]:
    _audio_to_audio_tab()

with transform_tabs[3]:
    _capability_tab(
        title="Video → Questions",
        description="Upload a lecture/explainer video. Get draft questions + answer key.",
        accept_types=["mp4", "mov", "webm", "mkv"],
        default_instruction=(
            "Generate 5 multiple-choice questions at the undergraduate level "
            "based strictly on this video's content."
        ),
        run=_run_video_questions,
        output_renderer=_render_questions_output,
        options_renderer=_video_questions_options,
        options_label="Question settings",
    )

with transform_tabs[4]:
    _capability_tab(
        title="Video → Professional",
        description=(
            "Upload an SME tutorial recording. Output: cleaned audio + captions "
            "+ stabilisation + light colour correction."
        ),
        accept_types=["mp4", "mov", "webm", "mkv"],
        default_instruction="",
        run=_run_video_enhance,
        output_renderer=_render_video_output,
        options_renderer=_video_enhance_options,
        options_label="Pipeline options",
    )

with transform_tabs[5]:
    _audio_questions_tab()

st.divider()
st.header("Generate New Content")
st.caption("No source material needed — describe what's wanted via a structured, validated prompt.")

generate_tab_titles = ["Generate Image", "Generate Audio"]
if SHOW_GENERATE_VIDEO:
    generate_tab_titles.append("Generate Video")
generate_tabs = st.tabs(generate_tab_titles)

with generate_tabs[0]:
    _generate_image_tab()

with generate_tabs[1]:
    _generate_audio_tab()

if SHOW_GENERATE_VIDEO:
    with generate_tabs[2]:
        _generate_video_tab()
