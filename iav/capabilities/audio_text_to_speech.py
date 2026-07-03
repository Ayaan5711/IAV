"""Text → Audio (Gemini TTS).

Takes a script (text) and returns studio-quality narration in the configured
voice preset. Output is WAV; the caller can convert to MP3 if ffmpeg is
available locally.
"""

from __future__ import annotations

import io
import logging
import os
import wave

from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput
from iav.models.config import Config, load_config
from iav.models.gemini_client import GeminiCallError, GeminiClient, get_client
from iav.models.pricing import summarize_costs
from iav.storage import save_output

logger = logging.getLogger(__name__)


class TextToSpeechError(RuntimeError):
    """Raised when TTS cannot produce audio."""


class TextToSpeech(Capability):
    name = "audio_text_to_speech"

    def __init__(self, client: GeminiClient | None = None, config: Config | None = None):
        self.config = config or load_config()
        self.client = client or get_client(self.config)
        self._settings = self.config.capability(self.name)

    def process(self, payload: CapabilityInput) -> CapabilityOutput:
        script = (payload.text or "").strip()
        if not script:
            raise ValueError("TextToSpeech requires text input (the script).")

        params = payload.params or {}
        instruction = (payload.instruction or "").strip() or self._settings.get("default_instruction", "")
        model = params.get("model") or os.environ.get("GEMINI_TTS_MODEL") or self._settings["model"]
        voice = params.get("voice") or self._settings.get("voice_preset", "Kore")
        sample_rate = int(self._settings.get("sample_rate_hz", 24000))

        logger.info(
            "audio_text_to_speech: model=%s voice=%s script_chars=%d",
            model,
            voice,
            len(script),
        )

        try:
            result = self.client.synthesize_speech(
                model=model,
                script=script,
                voice_preset=voice,
                instruction=instruction,
            )
        except GeminiCallError as exc:
            raise TextToSpeechError(f"Gemini TTS call failed: {exc}") from exc

        if not result.audio_bytes:
            note = (result.text or "").strip() or "(no detail)"
            raise TextToSpeechError(
                "Model returned no audio. This typically means a safety filter "
                "blocked the output, or the instruction was read literally "
                f"instead of as direction. Model said: {note}"
            )

        wav_bytes = _wrap_pcm_as_wav(result.audio_bytes, sample_rate=sample_rate)

        output_path = save_output(
            data=wav_bytes,
            suffix=".wav",
            capability=self.name,
        )

        cost = summarize_costs(
            [{"label": "tts", "model": model, "usage": result.usage}],
            self.config.pricing,
        )

        logger.info(
            "audio_text_to_speech: wrote %s (%d bytes, est. cost $%.6f)",
            output_path,
            len(wav_bytes),
            cost["total_usd"],
        )

        return CapabilityOutput(
            file_path=output_path,
            text=script,
            metadata={
                "model": model,
                "voice": voice,
                "sample_rate_hz": sample_rate,
                "mime_type": "audio/wav",
                "output_bytes": len(wav_bytes),
                "cost": cost,
            },
        )


def _wrap_pcm_as_wav(
    pcm_bytes: bytes,
    *,
    sample_rate: int = 24000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """Wrap raw L16 PCM (the format Gemini TTS returns) in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_bytes)
    return buf.getvalue()
