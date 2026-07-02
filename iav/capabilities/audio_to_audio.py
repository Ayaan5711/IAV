"""Audio → Audio.

Gemini has no native audio-in → audio-out path, so this is a three-step
pipeline:

    raw recording → ASR (audio → text)
                  → optional transcript cleanup (text → text)
                  → TTS (text → audio in the chosen voice preset)

The original speaker's voice is NOT preserved — output is in the configured
TTS voice. For the English listen-and-repeat use case that's intentional.
"""

from __future__ import annotations

import io
import logging
import mimetypes
import os
import wave
from pathlib import Path

from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput
from iav.models.config import Config, load_config
from iav.models.gemini_client import GeminiCallError, GeminiClient, get_client
from iav.models.pricing import summarize_costs
from iav.storage import save_output

logger = logging.getLogger(__name__)


class AudioToAudioError(RuntimeError):
    """Raised when the audio-to-audio pipeline cannot complete."""


class AudioToAudio(Capability):
    name = "audio_to_audio"

    def __init__(self, client: GeminiClient | None = None, config: Config | None = None):
        self.config = config or load_config()
        self.client = client or get_client(self.config)
        self._settings = self.config.capability(self.name)

    def process(self, payload: CapabilityInput) -> CapabilityOutput:
        if payload.file_path is None:
            raise ValueError("AudioToAudio requires an input audio file path")

        source = Path(payload.file_path)
        if not source.exists():
            raise FileNotFoundError(f"Input audio not found: {source}")

        audio_bytes = source.read_bytes()
        mime_type = _guess_audio_mime(source)
        asr_model = os.environ.get("GEMINI_ASR_MODEL") or self._settings["asr_model"]
        tts_model = os.environ.get("GEMINI_TTS_MODEL") or self._settings["tts_model"]
        voice = self._settings.get("voice_preset", "Kore")
        sample_rate = int(self._settings.get("sample_rate_hz", 24000))

        # 1. Transcribe ------------------------------------------------------
        logger.info(
            "audio_to_audio: transcribing model=%s file=%s (%d bytes)",
            asr_model,
            source.name,
            len(audio_bytes),
        )
        try:
            asr_result = self.client.transcribe_audio(
                model=asr_model,
                audio_bytes=audio_bytes,
                audio_mime_type=mime_type,
                instruction=self._settings.get("transcribe_instruction"),
            )
        except GeminiCallError as exc:
            raise AudioToAudioError(f"Gemini ASR call failed: {exc}") from exc

        transcript = (asr_result.text or "").strip()
        if not transcript:
            raise AudioToAudioError(
                "Transcription returned no text. The audio may be silent, "
                "in an unsupported format, or blocked by a safety filter."
            )

        # 2. Optional cleanup -----------------------------------------------
        cleaned = None
        if self._settings.get("cleanup_transcript", True):
            cleanup_instruction = self._settings.get("cleanup_instruction", "")
            logger.info("audio_to_audio: cleaning transcript")
            try:
                cleaned = self.client.generate_text(
                    model=asr_model,
                    prompt=f"{cleanup_instruction}\n\nTranscript:\n{transcript}",
                )
            except GeminiCallError:
                # Cleanup is best-effort — fall back to the raw transcript.
                logger.warning("Transcript cleanup failed; using raw transcript")
                script = transcript
            else:
                script = (cleaned.text or "").strip() or transcript
        else:
            script = transcript

        # 3. Synthesise speech ----------------------------------------------
        logger.info(
            "audio_to_audio: synthesising model=%s voice=%s script_chars=%d",
            tts_model,
            voice,
            len(script),
        )
        try:
            tts_result = self.client.synthesize_speech(
                model=tts_model,
                script=script,
                voice_preset=voice,
                instruction=(payload.instruction or "").strip() or None,
            )
        except GeminiCallError as exc:
            raise AudioToAudioError(f"Gemini TTS call failed: {exc}") from exc

        if not tts_result.audio_bytes:
            note = (tts_result.text or "").strip() or "(no detail)"
            raise AudioToAudioError(
                f"TTS returned no audio. Model said: {note}"
            )

        wav_bytes = _wrap_pcm_as_wav(tts_result.audio_bytes, sample_rate=sample_rate)

        output_path = save_output(
            data=wav_bytes,
            suffix=".wav",
            capability=self.name,
        )

        calls = [{"label": "transcribe", "model": asr_model, "usage": asr_result.usage}]
        if cleaned is not None:
            calls.append({"label": "cleanup", "model": asr_model, "usage": cleaned.usage})
        calls.append({"label": "synthesize", "model": tts_model, "usage": tts_result.usage})
        cost = summarize_costs(calls, self.config.pricing)

        logger.info(
            "audio_to_audio: wrote %s (%d bytes, est. cost $%.6f)",
            output_path,
            len(wav_bytes),
            cost["total_usd"],
        )

        return CapabilityOutput(
            file_path=output_path,
            text=script,
            metadata={
                "asr_model": asr_model,
                "tts_model": tts_model,
                "voice": voice,
                "input_file": str(source),
                "input_bytes": len(audio_bytes),
                "output_bytes": len(wav_bytes),
                "raw_transcript": transcript,
                "cleaned_script": script,
                "mime_type": "audio/wav",
                "cost": cost,
            },
        )


def _guess_audio_mime(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed and guessed.startswith("audio/"):
        return guessed
    suffix = path.suffix.lower().lstrip(".")
    fallback = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "m4a": "audio/mp4",
        "ogg": "audio/ogg",
        "flac": "audio/flac",
        "webm": "audio/webm",
    }
    if suffix in fallback:
        return fallback[suffix]
    raise ValueError(f"Unsupported audio format: {path.suffix}")


def _wrap_pcm_as_wav(
    pcm_bytes: bytes,
    *,
    sample_rate: int = 24000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_bytes)
    return buf.getvalue()
