"""Speech synthesis with a choice of engine: Azure Speech, Gemini, or both.

Mirrors iav/models/text_generation.py and image_generation.py's
engine-selection pattern, applied to TTS (audio_to_audio, audio_generate,
audio_question_generation).

Three engine modes, chosen per call (typically from a UI dropdown):
  auto:   Azure Speech primary if configured, Gemini as an automatic
          fallback.
  gemini: Gemini only -- Azure is never attempted. Required for
          multi-speaker narration (Azure Neural TTS here is single-voice
          only).
  azure:  Azure Speech only -- no fallback; fails loudly if unavailable or
          if a multi-speaker script is requested, since the caller
          explicitly asked for it.

Gemini's synthesize_speech() returns raw PCM that the caller wraps as WAV
itself; Azure Neural TTS returns an already-complete WAV container.
AudioSynthesisResult's `is_raw_pcm` flag tells the caller which shape it
got, so it doesn't double-wrap or mis-read the duration -- use
wav_duration_seconds() below for the Azure (already-WAV) case.
"""

from __future__ import annotations

import io
import logging
import wave
from dataclasses import dataclass
from typing import Any

from iav.models import azure_speech_client
from iav.models.gemini_client import GeminiCallError, GeminiClient

logger = logging.getLogger(__name__)


class AudioSynthesisError(RuntimeError):
    """Raised when the explicitly-selected TTS engine fails."""


@dataclass
class AudioSynthesisResult:
    audio_bytes: bytes
    is_raw_pcm: bool  # True: Gemini's raw PCM (caller wraps as WAV). False: already a WAV container (Azure).
    engine: str  # "azure-speech" | "gemini"
    call_record: dict[str, Any]  # ready to append to a capability's `calls` list


def wav_duration_seconds(wav_bytes: bytes) -> float:
    """Reads duration directly from a real WAV container's header -- for the
    Azure path, which returns a complete WAV file rather than raw PCM.
    """
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            return frames / rate if rate else 0.0
    except (wave.Error, EOFError) as exc:
        logger.warning("audio_generation: could not read WAV duration: %s", exc)
        return 0.0


def _call_gemini(
    gemini_client: GeminiClient, *, model: str, script: str, voice_preset: str | None,
    speakers: list[dict[str, str]] | None, instruction: str | None, label: str,
) -> AudioSynthesisResult:
    result = gemini_client.synthesize_speech(
        model=model, script=script, voice_preset=voice_preset, speakers=speakers, instruction=instruction,
    )
    if not result.audio_bytes:
        note = (result.text or "").strip() or "no detail"
        raise GeminiCallError(f"Model returned no audio: {note}")
    return AudioSynthesisResult(
        audio_bytes=result.audio_bytes,
        is_raw_pcm=True,
        engine="gemini",
        call_record={"label": label, "model": model, "usage": result.usage},
    )


def _call_azure(*, voice: str, script: str, label: str) -> AudioSynthesisResult:
    audio_bytes = azure_speech_client.synthesize_speech(script, voice=voice)
    return AudioSynthesisResult(
        audio_bytes=audio_bytes,
        is_raw_pcm=False,
        engine="azure-speech",
        call_record={"label": label, "model": "azure-neural-tts", "usage": None, "characters": len(script)},
    )


def synthesize_speech(
    *,
    gemini_client: GeminiClient,
    gemini_model: str,
    script: str,
    label: str,
    voice_preset: str | None = None,
    speakers: list[dict[str, str]] | None = None,
    instruction: str | None = None,
    azure_voice: str | None = None,
    engine: str = "auto",
) -> AudioSynthesisResult:
    engine = (engine or "auto").lower()

    if speakers and engine == "azure":
        raise AudioSynthesisError(
            f"Azure Speech was selected for '{label}' but multi-speaker narration needs Gemini -- "
            "switch engine to Gemini or Auto, or turn off multi-speaker."
        )

    # Multi-speaker always needs Gemini, even in auto mode -- Azure Neural
    # TTS here is single-voice only, so there's no point attempting it first.
    if engine == "gemini" or (speakers and engine == "auto"):
        try:
            return _call_gemini(
                gemini_client, model=gemini_model, script=script, voice_preset=voice_preset,
                speakers=speakers, instruction=instruction, label=label,
            )
        except GeminiCallError as exc:
            raise AudioSynthesisError(f"Gemini call failed for '{label}': {exc}") from exc

    if engine == "azure":
        if not azure_voice:
            raise AudioSynthesisError(f"Azure Speech was selected for '{label}' but no voice is configured.")
        try:
            return _call_azure(voice=azure_voice, script=script, label=label)
        except azure_speech_client.AzureSpeechUnavailable as exc:
            raise AudioSynthesisError(f"Azure Speech call failed for '{label}': {exc}") from exc

    # auto (single-voice): Azure primary, Gemini fallback -- never hard-fails
    # just because Azure isn't configured or a call to it fails.
    attempted_azure = bool(azure_voice) and azure_speech_client.is_configured()
    if attempted_azure:
        try:
            return _call_azure(voice=azure_voice, script=script, label=label)
        except azure_speech_client.AzureSpeechUnavailable as exc:
            logger.warning("Azure Speech TTS failed for '%s', falling back to Gemini: %s", label, exc)

    fallback_label = f"{label} (Gemini fallback)" if attempted_azure else label
    try:
        return _call_gemini(
            gemini_client, model=gemini_model, script=script, voice_preset=voice_preset,
            speakers=speakers, instruction=instruction, label=fallback_label,
        )
    except GeminiCallError as exc:
        raise AudioSynthesisError(f"Gemini call failed for '{label}': {exc}") from exc
