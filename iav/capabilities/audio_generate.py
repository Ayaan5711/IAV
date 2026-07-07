"""Generate Audio — structured prompt → new narrated audio.

Unlike audio_to_audio (which re-narrates an existing recording), this
generates narration from nothing. Two input modes:
  - topic:  a short brief. Gemini writes the actual narration script first,
            then narrates that -- otherwise TTS would just read the brief
            back verbatim instead of producing an explanation.
  - script: the user pastes the exact final script, narrated as-is.
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

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
from iav.models.text_generation import TextGenerationError, generate_text
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
        raw_text = (payload.text or payload.instruction or "").strip()
        params = payload.params or {}
        mode = params.get("mode", "topic")  # "topic" | "script"
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

        errors = validate_common_attributes(common) + validate_free_text(raw_text)
        if errors:
            raise ValueError("; ".join(errors))

        tts_model = os.environ.get("GEMINI_TTS_MODEL") or params.get("model") or self._settings["model"]
        text_model = params.get("text_model") or self._settings.get("text_model", tts_model)
        azure_deployment = self.config.azure_openai.get("default_deployment")
        engine = params.get("engine", "auto")
        sample_rate = int(self._settings.get("sample_rate_hz", 24000))

        calls: list[dict] = []

        if mode == "script":
            content = raw_text
        else:
            word_count = self._settings.get("length_word_counts", {}).get(length, 150)
            content_prompt = self._settings["content_instruction"].format(
                word_count=word_count, common_block=common_block(common), free_text=raw_text,
            )
            logger.info("audio_generate: writing narration content (target ~%d words)", word_count)
            try:
                content_result = generate_text(
                    gemini_client=self.client, gemini_model=text_model, prompt=content_prompt,
                    label="write_narration", azure_deployment=azure_deployment, engine=engine,
                )
            except (GeminiCallError, TextGenerationError) as exc:
                raise AudioGenerateError(f"Narration content generation failed: {exc}") from exc
            calls.append(content_result.call_record)
            content = content_result.text.strip()
            if not content:
                raise AudioGenerateError("Model returned no narration content.")

        prompt = self._settings["prompt_template"].format(
            tone=tone, speed=speed, accent=accent, length=length,
            common_block=common_block(common), free_text=content,
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
            "audio_generate: mode=%s tts_model=%s multi_speaker=%s accent=%s speed=%s tone=%s",
            mode, tts_model, multi_speaker, accent, speed, tone,
        )

        try:
            result = self.client.synthesize_speech(
                model=tts_model,
                script=prompt,
                voice_preset=None if speakers else voice,
                speakers=speakers,
            )
        except GeminiCallError as exc:
            raise AudioGenerateError(f"Gemini TTS call failed: {exc}") from exc
        calls.append({"label": "narrate", "model": tts_model, "usage": result.usage})

        if not result.audio_bytes:
            note = (result.text or "").strip() or "(no detail)"
            raise AudioGenerateError(f"Model returned no audio. Model said: {note}")

        wav_bytes = _wrap_pcm_as_wav(result.audio_bytes, sample_rate=sample_rate)
        duration_seconds = _pcm_duration_seconds(result.audio_bytes, sample_rate=sample_rate)

        requested_format = (params.get("output_format") or self._settings.get("output_format", "wav")).lower()
        output_bytes, actual_format, format_note = _maybe_convert_to_mp3(wav_bytes, requested_format)

        output_path = save_output(data=output_bytes, suffix=f".{actual_format}", capability=self.name)
        cost = summarize_costs(calls, self.config.pricing)

        logger.info(
            "audio_generate: wrote %s (%s), est. cost $%.6f", output_path, actual_format, cost["total_usd"]
        )

        return CapabilityOutput(
            file_path=output_path,
            text=prompt,
            metadata={
                "mode": mode,
                "narration_content": content,
                "tts_model": tts_model,
                "text_model": text_model,
                "multi_speaker": multi_speaker,
                "accent": accent,
                "speed": speed,
                "tone": tone,
                "length": length,
                "duration_seconds": duration_seconds,
                "output_bytes": len(output_bytes),
                "mime_type": "audio/mpeg" if actual_format == "mp3" else "audio/wav",
                "format_note": format_note,
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


def _pcm_duration_seconds(pcm_bytes: bytes, *, sample_rate: int, channels: int = 1, sample_width: int = 2) -> float:
    if sample_rate <= 0:
        return 0.0
    return len(pcm_bytes) / (sample_rate * channels * sample_width)


def _maybe_convert_to_mp3(wav_bytes: bytes, requested_format: str) -> tuple[bytes, str, str | None]:
    """Converts WAV -> MP3 via ffmpeg if requested and available.

    Returns (bytes, actual_format, note). Falls back to WAV with a note
    rather than silently mislabelling the file if ffmpeg isn't on PATH.
    """
    if requested_format != "mp3":
        return wav_bytes, "wav", None

    if not shutil.which("ffmpeg"):
        return wav_bytes, "wav", "mp3 requested but ffmpeg is not on PATH; returned wav instead."

    with tempfile.TemporaryDirectory(prefix="iav-audio-") as tmp:
        in_path = Path(tmp) / "in.wav"
        out_path = Path(tmp) / "out.mp3"
        in_path.write_bytes(wav_bytes)
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", str(in_path), "-codec:a", "libmp3lame", "-qscale:a", "2", str(out_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode != 0 or not out_path.exists():
            stderr_tail = (proc.stderr or b"").decode("utf-8", errors="replace")[-500:]
            return wav_bytes, "wav", f"mp3 conversion failed, returned wav instead: {stderr_tail}"
        return out_path.read_bytes(), "mp3", None
