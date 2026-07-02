"""Streamlit shell for the IAV media enhancement POC.

One tab per capability, all sharing the same upload → instruction → process →
result UX. Each tab delegates to a Capability implementation under
``iav.capabilities`` — the UI never references Gemini model IDs directly.
"""

from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import Callable

import streamlit as st

from iav.capabilities import CapabilityInput
from iav.capabilities.audio_question_generation import AudioQuestionGeneration
from iav.capabilities.audio_text_to_speech import TextToSpeech
from iav.capabilities.audio_to_audio import AudioToAudio
from iav.capabilities.image_enhance import ImageEnhance
from iav.capabilities.video_enhance import VideoEnhance
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
    """Running total of estimated cost across every call this session."""
    with st.sidebar:
        st.markdown("### Session cost (estimated)")
        total = st.session_state.get("session_cost_usd", 0.0)
        st.metric("Total this session", f"${total:.6f}")
        st.caption(
            "Sum of per-call cost estimates below. Token counts are real "
            "(from the API); dollar amounts are estimates from list-price "
            "rates — some unverified (flagged per call). Not a substitute "
            "for Cloud Billing."
        )
        if st.button("Reset session total", key="reset-session-cost"):
            st.session_state["session_cost_usd"] = 0.0
            st.rerun()


def _render_cost(metadata: dict | None) -> None:
    """Shared cost/token-usage display, shown under every result.

    Token counts here are real — pulled straight from each call's API
    response. Dollar amounts are estimates from the pricing table in
    config.yaml; any call using an unverified rate is flagged explicitly
    rather than blended silently into the total.
    """
    cost = (metadata or {}).get("cost")
    if not cost:
        return

    total = cost.get("total_usd", 0.0)
    calls = cost.get("calls", [])
    prompt_tok = cost.get("total_prompt_tokens", 0)
    output_tok = cost.get("total_output_tokens", 0)

    st.session_state["session_cost_usd"] = st.session_state.get("session_cost_usd", 0.0) + total

    label = f"Cost — est. ${total:.6f} this call ({prompt_tok:,} in / {output_tok:,} out tokens)"
    with st.expander(label, expanded=False):
        if cost.get("any_unverified"):
            st.warning(
                "One or more rates used below are UNVERIFIED against an "
                "official Google source — treat those numbers as "
                "directional, not authoritative."
            )
        for call in calls:
            badge = "verified" if call.get("verified") else "⚠ unverified"
            st.markdown(f"**{call.get('label', call.get('model'))}** — `{call.get('model')}` — {badge}")
            tok = call.get("tokens", {})
            cols = st.columns(3)
            cols[0].metric("Input tokens", f"{tok.get('prompt', 0):,}")
            cols[1].metric("Output tokens", f"{tok.get('output', 0):,}")
            cols[2].metric("Est. cost", f"${call.get('usd', 0.0):.6f}")
            breakdown = call.get("breakdown") or {}
            if breakdown:
                st.caption("Breakdown: " + ", ".join(f"{k}=${v:.6f}" for k, v in breakdown.items()))
            for note in call.get("notes", []):
                st.caption(f"ℹ {note}")
            st.divider()
        last_verified = cost.get("pricing_last_verified")
        source = cost.get("pricing_source_url")
        if last_verified or source:
            st.caption(f"Pricing table last verified: {last_verified or 'unknown'} — source: {source or 'n/a'}")


def _capability_tab(
    *,
    title: str,
    description: str,
    accept_types: list[str] | None,
    default_instruction: str,
    run: Callable[[Path, str], object],
    output_renderer: Callable[[object], None],
) -> None:
    """Generic tab: upload + instruction + process + result.

    Keeps every capability visually identical and reduces per-tab code to
    just the file types it accepts and how it renders its output.
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
                    result = run(saved, instruction)
                else:
                    result = run(text_input, instruction)
            output_renderer(result)
        except NotImplementedError as exc:
            st.info(f"Not yet implemented: {exc}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed: {exc}")
            with st.expander("Traceback"):
                st.code(traceback.format_exc())


# ----------------------------------------------------------------------
# Per-capability runners
# ----------------------------------------------------------------------


def _run_image(saved: Path, instruction: str):
    cap = ImageEnhance()
    return cap.process(CapabilityInput(file_path=saved, instruction=instruction))


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


def _run_text_to_speech(text: str, instruction: str):
    cap = TextToSpeech()
    return cap.process(CapabilityInput(text=text, instruction=instruction))


def _run_audio_to_audio(saved: Path, instruction: str):
    cap = AudioToAudio()
    return cap.process(CapabilityInput(file_path=saved, instruction=instruction))


def _run_video_questions(saved: Path, instruction: str):
    cap = VideoToQuestions()
    return cap.process(CapabilityInput(file_path=saved, instruction=instruction))


def _run_video_enhance(saved: Path, instruction: str):
    cap = VideoEnhance()
    return cap.process(CapabilityInput(file_path=saved, instruction=instruction))


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
    """Topic/passage -> narrated audio + text comprehension questions.

    Bespoke rather than routed through _capability_tab: this capability
    needs a mode selector (topic vs. pasted passage) plus explicit
    count/type/level controls, which the other tabs don't expose.
    """
    st.subheader("Audio → Questions — topic or passage → narrated audio + questions")
    st.caption(
        "Give a topic and Gemini writes a passage, or paste your own passage/script. "
        "Either way: narrated audio plus text comprehension questions with an answer key."
    )

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
            "e.g. Photosynthesis"
            if mode == "topic"
            else "Paste the full passage or script text here…"
        ),
        key="aq-text",
    )

    col1, col2, col3 = st.columns(3)
    count = col1.number_input("Number of questions", min_value=1, max_value=20, value=5, key="aq-count")
    qtype = col2.selectbox("Question type", ["mcq", "short_answer", "conceptual"], key="aq-type")
    level = col3.selectbox(
        "Level", ["school", "undergraduate", "postgraduate"], index=1, key="aq-level"
    )

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
    )

with tabs[5]:
    _audio_questions_tab()
