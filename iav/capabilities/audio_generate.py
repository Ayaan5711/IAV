"""Generate Audio — structured prompt → new narrated audio.

Unlike audio_to_audio (which re-narrates an existing recording), this
generates narration from nothing: assessment metadata + speaker/accent/
speed/tone/length attributes, sent straight to Gemini TTS.
"""

from __future__ import annotations

import io
import logging
import os
import wave

from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput
from iav.capabilities.prompt_schema import (
    CommonAttributes,
    common_block,
    validate_common_attributes,
    validate_free_text,
)
from iav.models.config import Config, load_config
from iav.models.gemini_client import GeminiCallError, GeminiClient, get_client
from iav.models.pricing import summarize_costs
from iav.storage import save_output

logger = logging.getLogger(__name__)

_MULTI_SPEAKER_VOICES = ["Kore", "Puck"]


class AudioGenerateError(RuntimeError):
    """Raised when audio generation cannot produce an output."""


class AudioGenerate(Capability):
    name = "audio_generate"

    def __init__(self, client: GeminiClient | None = None, config: Config | None = None):
        self.config = config or load_config()
        self.client = client or get_client(self.config)
        self._settings = self.config.capability(self.name)

    def process(self, payload: CapabilityInput) -> CapabilityOutput:
        free_text = (payload.text or payload.instruction or "").strip()
        params = payload.params or {}
        common = CommonAttributes(
            assessment_outcome=params.get("assessment_outcome", ""),
            difficulty_level=params.get("difficulty_level", "medium"),
            target_audience=params.get("target_audience", "undergraduate"),
            question_type=params.get("question_type", "mcq"),
        )
        accent = params.get("accent") or self._settings["accents"][0]
        speed = params.get("speed") or self._settings["speeds"][0]
        tone = params.get("tone") or self._settings["tones"][0]
        length = params.get("length") or self._settings["lengths"][0]
        multi_speaker = bool(params.get("multi_speaker", False))
        voice = params.get("voice") or self._settings.get("voice_preset", "Kore")

        errors = validate_common_attributes(common) + validate_free_text(free_text)
        if errors:
            raise ValueError("; ".join(errors))

        model = os.environ.get("GEMINI_TTS_MODEL") or params.get("model") or self._settings["model"]
        sample_rate = int(self._settings.get("sample_rate_hz", 24000))

        prompt = self._settings["prompt_template"].format(
            tone=tone, speed=speed, accent=accent, length=length,
            common_block=common_block(common), free_text=free_text,
        )

        speakers = None
        if multi_speaker:
            speakers = [
                {"speaker": "Speaker1", "voice": _MULTI_SPEAKER_VOICES[0]},
                {"speaker": "Speaker2", "voice": _MULTI_SPEAKER_VOICES[1]},
            ]
            prompt += (
                "\n\nRender this as a two-speaker dialogue. Label each line "
                "'Speaker1:' or 'Speaker2:' before narrating it."
            )

        logger.info(
            "audio_generate: model=%s multi_speaker=%s accent=%s speed=%s tone=%s",
            model, multi_speaker, accent, speed, tone,
        )

        try:
            result = self.client.synthesize_speech(
                model=model,
                script=prompt,
                voice_preset=None if speakers else voice,
                speakers=speakers,
            )
        except GeminiCallError as exc:
            raise AudioGenerateError(f"Gemini TTS call failed: {exc}") from exc

        if not result.audio_bytes:
            note = (result.text or "").strip() or "(no detail)"
            raise AudioGenerateError(f"Model returned no audio. Model said: {note}")

        wav_bytes = _wrap_pcm_as_wav(result.audio_bytes, sample_rate=sample_rate)
        output_path = save_output(data=wav_bytes, suffix=".wav", capability=self.name)
        cost = summarize_costs(
            [{"label": "audio_generate", "model": model, "usage": result.usage}],
            self.config.pricing,
        )

        logger.info("audio_generate: wrote %s, est. cost $%.6f", output_path, cost["total_usd"])

        return CapabilityOutput(
            file_path=output_path,
            text=prompt,
            metadata={
                "model": model,
                "multi_speaker": multi_speaker,
                "accent": accent,
                "speed": speed,
                "tone": tone,
                "length": length,
                "output_bytes": len(wav_bytes),
                "mime_type": "audio/wav",
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
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_bytes)
    return buf.getvalue()
