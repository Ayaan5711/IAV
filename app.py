"""Streamlit shell for the IAV media enhancement POC.

Two families of tabs, both sharing the same Process → result → cost UX:

  - Enhance/analyse: transform SME-supplied content (sketch, recording, video)
  - Generate: create new media from a structured, validated prompt

The UI never references a Gemini model ID directly except as a value pulled
from config.yaml's available_* lists — every dropdown's options come from
config, not from hardcoded Python.
"""

from __future__ import annotations

import logging
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
            st.error(f"Config error: {exc}")
            return False

        st.success(f"Vertex AI project: `{cfg.vertex.project_id}`")
        st.caption(f"Location: `{cfg.vertex.location}`")
        st.caption(f"Credentials: `{cfg.vertex.credentials_path}`")
        return True


def _show_session_cost() -> None:
    with st.sidebar:
        st.markdown("### Session cost (estimated)")
        total = st.session_state.get("session_cost_usd", 0.0)
        st.metric("Total this session", f"${total:.6f}")
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

    label = f"Cost — est. ${total:.6f} ({prompt_tok:,} in / {output_tok:,} out tokens)"
    with st.expander(label, expanded=False):
        if cost.get("any_unverified"):
            st.warning("Some rates below are unverified against an official Google source.")
        for call in calls:
            badge = "verified" if call.get("verified") else "⚠ unverified"
            st.markdown(f"**{call.get('label', call.get('model'))}** — `{call.get('model')}` — {badge}")
            tok = call.get("tokens", {})
            cols = st.columns(4)
            cols[0].metric("Input tokens", f"{tok.get('prompt', 0):,}")
            cols[1].metric("Output tokens", f"{tok.get('output', 0):,}")
            cols[2].metric("Input cost", f"${call.get('input_usd', 0.0):.6f}")
            cols[3].metric("Output cost", f"${call.get('output_usd', 0.0):.6f}")
            for note in call.get("notes", []):
                st.caption(f"ℹ {note}")
            st.divider()
        last_verified = cost.get("pricing_last_verified")
        source = cost.get("pricing_source_url")
        if last_verified or source:
            st.caption(f"Pricing last verified {last_verified or 'unknown'} — {source or 'n/a'}")


def _capability_tab(
    *,
    title: str,
    description: str,
    accept_types: list[str] | None,
    default_instruction: str,
    run: Callable[[Any, str, dict], object],
    output_renderer: Callable[[object], None],
    options_renderer: Callable[[], dict] | None = None,
) -> None:
    """Generic tab: upload/text → options → instruction → process → result."""
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

    params = options_renderer() if options_renderer else {}

    instruction = st.text_area(
        "Instruction (optional — leave blank to use the default)",
        value="",
        placeholder=default_instruction,
        height=120,
        key=f"instruction-{title}",
    )

    if st.button("Process", type="primary", key=f"go-{title}"):
        if accept_types is not None and uploaded is None:
            st.warning("Upload a file first.")
            return
        if accept_types is None and not (text_input or "").strip():
            st.warning("Enter some text first.")
            return

        try:
            with st.spinner("Working…"):
                if accept_types is not None:
                    suffix = Path(uploaded.name).suffix or ""
                    saved = save_input(uploaded.getvalue(), suffix)
                    result = run(saved, instruction, params)
                else:
                    result = run(text_input, instruction, params)
            output_renderer(result)
        except NotImplementedError as exc:
            st.info(f"Not yet implemented: {exc}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed: {exc}")
            with st.expander("Traceback"):
                st.code(traceback.format_exc())


def _common_attributes_form(key_prefix: str) -> CommonAttributes:
    """The four assessment-metadata fields shared by every generate tab."""
    st.markdown("**Assessment metadata**")
    outcome = st.text_input(
        "Assessment outcome",
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
# Enhance / analyse tabs — transform SME-supplied content
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


def _audio_to_audio_options() -> dict:
    s = load_config().capability("audio_to_audio")
    cols = st.columns(3)
    asr_models = s.get("available_asr_models") or [s["asr_model"]]
    asr_model = cols[0].selectbox("ASR model", asr_models, index=_idx(asr_models, s["asr_model"]), key="a2a-asr")
    tts_models = s.get("available_tts_models") or [s["tts_model"]]
    tts_model = cols[1].selectbox("TTS model", tts_models, index=_idx(tts_models, s["tts_model"]), key="a2a-tts")
    voices = s.get("available_voices") or [s.get("voice_preset", "Kore")]
    voice = cols[2].selectbox("Voice", voices, index=_idx(voices, s.get("voice_preset")), key="a2a-voice")
    return {"asr_model": asr_model, "tts_model": tts_model, "voice": voice}


def _run_audio_to_audio(saved: Path, instruction: str, params: dict):
    cap = AudioToAudio()
    return cap.process(CapabilityInput(file_path=saved, instruction=instruction, params=params))


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
        if result.metadata and result.metadata.get("raw_transcript"):
            with st.expander("Transcript"):
                st.text(result.metadata["raw_transcript"])
            if result.metadata.get("cleaned_script") and result.metadata["cleaned_script"] != result.metadata["raw_transcript"]:
                with st.expander("Cleaned script used for TTS"):
                    st.text(result.metadata["cleaned_script"])
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

    st.markdown("**Pipeline steps**")
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


def _audio_questions_tab() -> None:
    """Topic/passage -> narrated audio + text comprehension questions."""
    st.subheader("Audio → Questions — topic or passage → narrated audio + questions")
    st.caption(
        "Give a topic and Gemini writes a passage, or paste your own passage/script. "
        "Either way: narrated audio plus text comprehension questions with an answer key."
    )

    s = load_config().capability("audio_question_generation")

    mode_label = st.radio(
        "Input type",
        ["Topic (Gemini writes the passage)", "My own passage/script"],
        key="aq-mode",
        horizontal=True,
    )
    mode = "topic" if mode_label.startswith("Topic") else "passage"

    text_input = st.text_area(
        "Topic" if mode == "topic" else "Passage / script",
        height=140,
        placeholder=(
            "e.g. Photosynthesis" if mode == "topic" else "Paste the full passage or script text here…"
        ),
        key="aq-text",
    )

    cols = st.columns(3)
    count = cols[0].number_input("Number of questions", min_value=1, max_value=20, value=5, key="aq-count")
    qtype = cols[1].selectbox("Question type", ["mcq", "short_answer", "conceptual"], key="aq-type")
    level = cols[2].selectbox("Level", ["school", "undergraduate", "postgraduate"], index=1, key="aq-level")

    cols2 = st.columns(2)
    text_models = s.get("available_text_models") or [s["text_model"]]
    text_model = cols2[0].selectbox("Text model", text_models, index=_idx(text_models, s["text_model"]), key="aq-textmodel")
    voices = s.get("available_voices") or [s.get("voice_preset", "Kore")]
    voice = cols2[1].selectbox("Voice", voices, index=_idx(voices, s.get("voice_preset")), key="aq-voice")

    instruction = st.text_area(
        "Narration instruction (optional — leave blank to use the default)",
        value="",
        height=80,
        key="aq-instruction",
    )

    if st.button("Process", type="primary", key="aq-go"):
        if not (text_input or "").strip():
            st.warning("Enter a topic or a passage first.")
            return
        try:
            with st.spinner("Working…"):
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
                        },
                    )
                )
            _render_audio_questions_output(result)
        except NotImplementedError as exc:
            st.info(f"Not yet implemented: {exc}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed: {exc}")
            with st.expander("Traceback"):
                st.code(traceback.format_exc())


def _render_audio_questions_output(result) -> None:  # type: ignore[no-untyped-def]
    meta = result.metadata or {}
    st.success(f"Done — generated {meta.get('question_count', '?')} questions.")
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
# Generate tabs — new media from a structured, validated prompt
# ----------------------------------------------------------------------


def _generate_image_tab() -> None:
    st.subheader("Generate Image — structured prompt → new exam image")
    st.caption("No sketch needed — describe what's wanted and Gemini generates it from scratch.")

    s = load_config().capability("image_generate")
    common = _common_attributes_form("gi")

    cols = st.columns(2)
    visual_type = cols[0].selectbox("Visual type", s["visual_types"], key="gi-visual")
    style = cols[1].selectbox("Style", s["styles"], key="gi-style")

    cols2 = st.columns(3)
    models = s.get("available_models") or [s["model"]]
    model = cols2[0].selectbox("Model", models, index=_idx(models, s["model"]), key="gi-model")
    resolutions = s.get("available_resolutions") or [s.get("resolution", "2K")]
    resolution = cols2[1].selectbox("Resolution", resolutions, index=_idx(resolutions, s.get("resolution")), key="gi-res")
    formats = s.get("available_formats") or [s.get("output_format", "png")]
    output_format = cols2[2].selectbox("Format (for CAE compatibility)", formats, index=_idx(formats, s.get("output_format")), key="gi-fmt")

    free_text = st.text_area(
        "Describe the image",
        height=120,
        placeholder="e.g. A right triangle with legs 3 and 4, hypotenuse labelled c",
        key="gi-freetext",
    )

    if st.button("Generate", type="primary", key="gi-go"):
        errors = validate_common_attributes(common) + validate_free_text(free_text)
        if not _show_validation_errors(errors):
            return
        try:
            with st.spinner("Generating…"):
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
            st.success("Done.")
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
            st.error(f"Failed: {exc}")
            with st.expander("Traceback"):
                st.code(traceback.format_exc())


def _generate_audio_tab() -> None:
    st.subheader("Generate Audio — structured prompt → new narration")
    st.caption("No recording needed — describe the content and delivery, Gemini narrates it from scratch.")

    s = load_config().capability("audio_generate")
    common = _common_attributes_form("ga")

    cols = st.columns(2)
    speaker_mode = cols[0].selectbox("Speakers", s["speaker_modes"], key="ga-speakers")
    multi_speaker = speaker_mode == "Multiple speakers"
    accent = cols[1].selectbox("Accent", s["accents"], key="ga-accent")

    cols2 = st.columns(2)
    speed = cols2[0].selectbox("Speed", s["speeds"], key="ga-speed")
    tone = cols2[1].selectbox("Tone", s["tones"], key="ga-tone")

    cols3 = st.columns(3)
    length = cols3[0].selectbox("Length", s["lengths"], key="ga-length")
    models = s.get("available_models") or [s["model"]]
    model = cols3[1].selectbox("Model", models, index=_idx(models, s["model"]), key="ga-model")
    voices = s.get("available_voices") or [s.get("voice_preset", "Kore")]
    voice = cols3[2].selectbox(
        "Voice (single-speaker only)", voices, index=_idx(voices, s.get("voice_preset")),
        key="ga-voice", disabled=multi_speaker,
    )

    free_text = st.text_area(
        "Content to narrate",
        height=140,
        placeholder="e.g. Explain the water cycle in three stages: evaporation, condensation, precipitation.",
        key="ga-freetext",
    )

    if st.button("Generate", type="primary", key="ga-go"):
        errors = validate_common_attributes(common) + validate_free_text(free_text)
        if not _show_validation_errors(errors):
            return
        try:
            with st.spinner("Generating…"):
                cap = AudioGenerate()
                result = cap.process(
                    CapabilityInput(
                        text=free_text,
                        params={
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
                            "voice": voice,
                        },
                    )
                )
            st.success("Done.")
            st.audio(str(result.file_path))
            with result.file_path.open("rb") as fh:
                st.download_button(
                    "Download", data=fh.read(), file_name=result.file_path.name, mime="audio/wav"
                )
            with st.expander("Prompt sent to Gemini"):
                st.text(result.text or "")
            _render_cost(result.metadata)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed: {exc}")
            with st.expander("Traceback"):
                st.code(traceback.format_exc())


def _generate_video_tab() -> None:
    st.subheader("Generate Video — structured prompt → new scenario clip (Veo)")
    st.caption(
        "Real constraints: Preview-only model, 4-8 second clips, generation can take several minutes, "
        "billed per second of output. This produces one short clip, not a full scenario film."
    )

    s = load_config().capability("video_generate")
    common = _common_attributes_form("gv")

    cols = st.columns(3)
    models = s.get("available_models") or [s["model"]]
    model = cols[0].selectbox("Model", models, index=_idx(models, s["model"]), key="gv-model")
    resolutions = s.get("available_resolutions") or [s.get("resolution", "720p")]
    resolution = cols[1].selectbox("Resolution", resolutions, index=_idx(resolutions, s.get("resolution")), key="gv-res")
    durations = s.get("available_durations_seconds") or [s.get("duration_seconds", 8)]
    duration = cols[2].selectbox(
        "Length (seconds)", durations, index=_idx(durations, s.get("duration_seconds")), key="gv-dur"
    )

    generate_audio = st.checkbox("Generate audio with the video", value=s.get("generate_audio", True), key="gv-audio")

    free_text = st.text_area(
        "Scenario",
        height=140,
        placeholder="e.g. A student measuring the angle of a ramp with a protractor in a physics lab",
        key="gv-freetext",
    )

    if st.button("Generate", type="primary", key="gv-go"):
        errors = validate_common_attributes(common) + validate_free_text(free_text)
        if not _show_validation_errors(errors):
            return
        try:
            with st.spinner(f"Generating video — this can take a few minutes (Veo, up to {int(s.get('poll_timeout_seconds', 360))}s)…"):
                cap = VideoGenerate()
                result = cap.process(
                    CapabilityInput(
                        text=free_text,
                        params={
                            "assessment_outcome": common.assessment_outcome,
                            "difficulty_level": common.difficulty_level,
                            "target_audience": common.target_audience,
                            "question_type": common.question_type,
                            "model": model,
                            "resolution": resolution,
                            "duration_seconds": int(duration),
                            "generate_audio": generate_audio,
                        },
                    )
                )
            st.success("Done.")
            st.video(str(result.file_path))
            with result.file_path.open("rb") as fh:
                st.download_button(
                    "Download MP4", data=fh.read(), file_name=result.file_path.name, mime="video/mp4"
                )
            with st.expander("Prompt sent to Veo"):
                st.text(result.text or "")
            _render_cost(result.metadata)
        except Exception as exc:  # noqa: BLE001
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

tabs = st.tabs([
    "Image",
    "Text → Audio",
    "Audio → Audio",
    "Video → Questions",
    "Video → Professional",
    "Audio → Questions",
    "Generate Image",
    "Generate Audio",
    "Generate Video",
])

with tabs[0]:
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
    )

with tabs[1]:
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
    )

with tabs[2]:
    _capability_tab(
        title="Audio → Audio",
        description=(
            "Upload a raw recording. Transcribed and re-spoken in the chosen "
            "voice preset (original speaker's voice is not preserved)."
        ),
        accept_types=["mp3", "wav", "m4a", "ogg", "flac"],
        default_instruction="",
        run=_run_audio_to_audio,
        output_renderer=_render_audio_output,
        options_renderer=_audio_to_audio_options,
    )

with tabs[3]:
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
    )

with tabs[4]:
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
    )

with tabs[5]:
    _audio_questions_tab()

with tabs[6]:
    _generate_image_tab()

with tabs[7]:
    _generate_audio_tab()

with tabs[8]:
    _generate_video_tab()
