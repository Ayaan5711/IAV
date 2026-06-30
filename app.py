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
        with result.file_path.open("rb") as fh:
            st.download_button(
                "Download",
                data=fh.read(),
                file_name=result.file_path.name,
                mime="audio/mpeg",
            )


def _render_questions_output(result) -> None:  # type: ignore[no-untyped-def]
    st.success("Done.")
    if result.data:
        st.json(result.data)
    elif result.text:
        st.code(result.text)


def _render_video_output(result) -> None:  # type: ignore[no-untyped-def]
    st.success("Done.")
    if result.file_path:
        st.video(str(result.file_path))


# ----------------------------------------------------------------------
# Page layout
# ----------------------------------------------------------------------


st.title("IAV — Gemini Media Enhancement")
st.caption("POC for SME content authoring. Built on Vertex AI.")

_config_ok = _show_config_status()

tabs = st.tabs([
    "Image",
    "Text → Audio",
    "Audio → Audio",
    "Video → Questions",
    "Video → Professional",
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
