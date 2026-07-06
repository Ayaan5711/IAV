"""Audio → Audio.

Two input modes:
    upload: raw recording -> transcription -> optional cleanup -> TTS
            -> comprehension questions generated from the transcript.
    topic:  a topic/scenario brief -> Gemini writes the narration content
            directly -> TTS -> questions. No transcription step.

Transcription tries Azure Speech first (multilingual, including Indian
languages, and more robust to background noise than prompting a
general-purpose model) and falls back to Gemini ASR if Azure isn't
configured or the call fails -- this pipeline never hard-fails just
because Azure credentials aren't present.

The original speaker's voice is NOT preserved — output uses the voice preset.
"""

from __future__ import annotations

import io
import json
import logging
import mimetypes
import wave
from pathlib import Path
from typing import Any

from iav.capabilities._json_utils import JsonParseError, parse_json_loose, questions_as_markdown
from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput
from iav.models import azure_speech_client
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
        params = payload.params or {}
        mode = params.get("mode", "upload")  # "upload" | "topic"
        question_model = params.get("question_model") or self._settings["question_model"]
        tts_model = params.get("tts_model") or self._settings["tts_model"]
        voice = params.get("voice") or self._settings.get("voice_preset", "Kore")
        sample_rate = int(self._settings.get("sample_rate_hz", 24000))
        count = int(params.get("count", self._settings.get("default_question_count", 5)))
        qtype = params.get("type") or self._settings.get("default_question_type", "mcq")
        level = params.get("level") or self._settings.get("default_level", "undergraduate")

        calls: list[dict[str, Any]] = []
        raw_transcript: str | None = None
        asr_engine: str | None = None
        language: str | None = None

        if mode == "upload":
            if payload.file_path is None:
                raise ValueError("AudioToAudio (upload mode) requires an input audio file")
            source = Path(payload.file_path)
            if not source.exists():
                raise FileNotFoundError(f"Input audio not found: {source}")
            audio_bytes = source.read_bytes()
            language = params.get("language") or self._settings.get("default_language", "en-US")

            transcript = None
            if azure_speech.is_configured():
                logger.info("audio_to_audio: transcribing via Azure Speech (language=%s)", language)
                try:
                    azure_result = azure_speech.transcribe_file(source, language=language)
                    transcript = azure_result.text
                    asr_engine = f"Azure Speech ({language})"
                except azure_speech.AzureSpeechUnavailable as exc:
                    logger.warning("Azure Speech transcription failed, falling back to Gemini ASR: %s", exc)
            else:
                logger.info("audio_to_audio: Azure Speech not configured, using Gemini ASR")

            if transcript is None:
                mime_type = _guess_audio_mime(source)
                try:
                    asr_result = self.client.transcribe_audio(
                        model=question_model,
                        audio_bytes=audio_bytes,
                        audio_mime_type=mime_type,
                        instruction=self._settings.get("transcribe_instruction"),
                    )
                except GeminiCallError as exc:
                    raise AudioToAudioError(f"Gemini ASR call failed: {exc}") from exc
                calls.append({"label": "transcribe (Gemini fallback)", "model": question_model, "usage": asr_result.usage})
                transcript = (asr_result.text or "").strip()
                asr_engine = f"Gemini ASR fallback ({question_model})"

            transcript = (transcript or "").strip()
            if not transcript:
                raise AudioToAudioError(
                    "Transcription returned no text. The audio may be silent, "
                    "in an unsupported format, or blocked by a safety filter."
                )
            raw_transcript = transcript

            if self._settings.get("cleanup_transcript", True):
                cleanup_instruction = self._settings.get("cleanup_instruction", "")
                logger.info("audio_to_audio: cleaning transcript")
                try:
                    cleaned = self.client.generate_text(
                        model=question_model,
                        prompt=f"{cleanup_instruction}\n\nTranscript:\n{transcript}",
                    )
                except GeminiCallError:
                    logger.warning("Transcript cleanup failed; using raw transcript")
                    script = transcript
                else:
                    calls.append({"label": "cleanup", "model": question_model, "usage": cleaned.usage})
                    script = (cleaned.text or "").strip() or transcript
            else:
                script = transcript
        else:
            raw_text = (payload.text or payload.instruction or "").strip()
            if not raw_text:
                raise ValueError("AudioToAudio (topic mode) requires a topic/scenario")
            length = params.get("length") or self._settings["lengths"][0]
            word_count = self._settings.get("length_word_counts", {}).get(length, 150)
            content_prompt = self._settings["content_instruction"].format(word_count=word_count, free_text=raw_text)
            logger.info("audio_to_audio: writing narration content (target ~%d words)", word_count)
            try:
                content_result = self.client.generate_text(model=question_model, prompt=content_prompt)
            except GeminiCallError as exc:
                raise AudioToAudioError(f"Content generation failed: {exc}") from exc
            calls.append({"label": "write_content", "model": question_model, "usage": content_result.usage})
            script = (content_result.text or "").strip()
            if not script:
                raise AudioToAudioError("Model returned no content.")

        # Synthesise speech ---------------------------------------------------
        tts_instruction = (payload.instruction or "").strip() or None if mode == "upload" else None
        logger.info("audio_to_audio: synthesising model=%s voice=%s script_chars=%d", tts_model, voice, len(script))
        try:
            tts_result = self.client.synthesize_speech(
                model=tts_model,
                script=script,
                voice_preset=voice,
                instruction=tts_instruction,
            )
        except GeminiCallError as exc:
            raise AudioToAudioError(f"Gemini TTS call failed: {exc}") from exc
        calls.append({"label": "synthesize", "model": tts_model, "usage": tts_result.usage})

        if not tts_result.audio_bytes:
            note = (tts_result.text or "").strip() or "(no detail)"
            raise AudioToAudioError(f"TTS returned no audio. Model said: {note}")

        wav_bytes = _wrap_pcm_as_wav(tts_result.audio_bytes, sample_rate=sample_rate)
        duration_seconds = _pcm_duration_seconds(tts_result.audio_bytes, sample_rate=sample_rate)
        output_path = save_output(data=wav_bytes, suffix=".wav", capability=self.name)

        # Generate comprehension questions from the script --------------------
        q_prompt = self._settings["questions_instruction"].format(
            count=count, question_type=qtype, level=level, passage=script
        )
        logger.info("audio_to_audio: generating questions")
        try:
            q_result = self.client.generate_text(
                model=question_model, prompt=q_prompt, response_mime_type="application/json"
            )
        except GeminiCallError as exc:
            raise AudioToAudioError(f"Question generation failed: {exc}") from exc
        calls.append({"label": "generate_questions", "model": question_model, "usage": q_result.usage})

        q_raw = (q_result.text or "").strip()
        if not q_raw:
            raise AudioToAudioError("Model returned no question text.")
        try:
            parsed = parse_json_loose(q_raw)
        except JsonParseError as exc:
            raise AudioToAudioError(str(exc)) from exc

        questions = parsed.get("questions") if isinstance(parsed, dict) else None
        if not isinstance(questions, list) or not questions:
            raise AudioToAudioError("Model returned no usable questions.")

        json_bytes = json.dumps(parsed, indent=2, ensure_ascii=False).encode("utf-8")
        json_path = save_output(data=json_bytes, suffix=".json", capability=f"{self.name}-questions")

        cost = summarize_costs(calls, self.config.pricing)

        logger.info(
            "audio_to_audio: wrote %s + %s (mode=%s, asr_engine=%s, %d questions, est. cost $%.6f)",
            output_path, json_path, mode, asr_engine, len(questions), cost["total_usd"],
        )

        return CapabilityOutput(
            file_path=output_path,
            text=script,
            data=parsed,
            metadata={
                "mode": mode,
                "language": language,
                "asr_engine": asr_engine,
                "question_model": question_model,
                "tts_model": tts_model,
                "voice": voice,
                "raw_transcript": raw_transcript,
                "cleaned_script": script,
                "duration_seconds": duration_seconds,
                "question_count": len(questions),
                "questions_json_path": str(json_path),
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


def _pcm_duration_seconds(pcm_bytes: bytes, *, sample_rate: int, channels: int = 1, sample_width: int = 2) -> float:
    if sample_rate <= 0:
        return 0.0
    return len(pcm_bytes) / (sample_rate * channels * sample_width)
