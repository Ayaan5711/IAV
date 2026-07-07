"""Audio → Audio.

Three input modes:
    upload: raw recording -> transcription -> optional cleanup -> TTS.
    topic:  a topic/scenario brief -> Gemini writes the narration content
            directly -> TTS. No transcription step.
    script: an exact script pasted verbatim -> TTS, no rewriting at all --
            this is the same "paste a script, narrate it" use case the
            separate Text-to-Audio tab used to cover.

Optionally (toggle in the UI), also generates comprehension questions from
the final script -- off by default, since not every use of this tab wants
a quiz on top of the audio.

Optionally, the script can be translated into a different output language
before narration (see iav/models/text_generation.py's translate_text()) --
default is "Same as input", meaning no translation happens at all.

Transcription tries Azure Speech first (multilingual) and falls back to
Gemini ASR if Azure isn't configured or the call fails -- this pipeline
never hard-fails just because Azure credentials aren't present.

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

from iav.capabilities._json_utils import JsonParseError, parse_json_loose
from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput
from iav.models import azure_speech_client
from iav.models.config import Config, load_config
from iav.models.gemini_client import GeminiCallError, GeminiClient, get_client
from iav.models.pricing import summarize_costs
from iav.models.text_generation import TextGenerationError, generate_text, translate_text
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
        mode = params.get("mode", "upload")  # "upload" | "topic" | "script"
        question_model = params.get("question_model") or self._settings["question_model"]
        tts_model = params.get("tts_model") or self._settings["tts_model"]
        voice = params.get("voice") or self._settings.get("voice_preset", "Kore")
        sample_rate = int(self._settings.get("sample_rate_hz", 24000))
        azure_deployment = self.config.azure_openai.get("default_deployment")
        engine = params.get("engine", "auto")
        target_language = params.get("target_language") or self.config.languages.get(
            "default_output_language", "Same as input"
        )
        want_questions = bool(params.get("generate_questions", False))
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
            language = params.get("language") or self.config.languages.get("default_input_locale", "en-US")

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
                    cleaned = generate_text(
                        gemini_client=self.client, gemini_model=question_model,
                        prompt=f"{cleanup_instruction}\n\nTranscript:\n{transcript}",
                        label="cleanup", azure_deployment=azure_deployment, engine=engine,
                    )
                except (GeminiCallError, TextGenerationError):
                    logger.warning("Transcript cleanup failed; using raw transcript")
                    script = transcript
                else:
                    calls.append(cleaned.call_record)
                    script = cleaned.text.strip() or transcript
            else:
                script = transcript
        elif mode == "script":
            raw_text = (payload.text or payload.instruction or "").strip()
            if not raw_text:
                raise ValueError("AudioToAudio (script mode) requires an exact script")
            script = raw_text
        else:
            raw_text = (payload.text or payload.instruction or "").strip()
            if not raw_text:
                raise ValueError("AudioToAudio (topic mode) requires a topic/scenario")
            length = params.get("length") or self._settings["lengths"][0]
            word_count = self._settings.get("length_word_counts", {}).get(length, 150)
            content_prompt = self._settings["content_instruction"].format(word_count=word_count, free_text=raw_text)
            logger.info("audio_to_audio: writing narration content (target ~%d words)", word_count)
            try:
                content_result = generate_text(
                    gemini_client=self.client, gemini_model=question_model, prompt=content_prompt,
                    label="write_content", azure_deployment=azure_deployment, engine=engine,
                )
            except (GeminiCallError, TextGenerationError) as exc:
                raise AudioToAudioError(f"Content generation failed: {exc}") from exc
            calls.append(content_result.call_record)
            script = content_result.text.strip()
            if not script:
                raise AudioToAudioError("Model returned no content.")

        # Translate into a different output language, if requested ------------
        if target_language and target_language != "Same as input":
            translate_template = self.config.languages.get("translate_instruction")
            if not translate_template:
                raise AudioToAudioError("No translate_instruction configured under languages: in config.yaml.")
            logger.info("audio_to_audio: translating script into %s", target_language)
            try:
                translated = translate_text(
                    gemini_client=self.client, gemini_model=question_model, text=script,
                    target_language=target_language, translate_instruction_template=translate_template,
                    azure_deployment=azure_deployment, engine=engine,
                )
            except (GeminiCallError, TextGenerationError) as exc:
                raise AudioToAudioError(f"Translation to {target_language} failed: {exc}") from exc
            calls.append(translated.call_record)
            script = translated.text.strip() or script

        # Synthesise speech ---------------------------------------------------
        tts_instruction = (payload.instruction or "").strip() or None if mode != "topic" else None
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

        # Generate comprehension questions from the script (optional) ---------
        questions: list | None = None
        parsed: dict | None = None
        json_path: Path | None = None
        if want_questions:
            q_prompt = self._settings["questions_instruction"].format(
                count=count, question_type=qtype, level=level, passage=script
            )
            logger.info("audio_to_audio: generating questions")
            try:
                q_result = generate_text(
                    gemini_client=self.client, gemini_model=question_model, prompt=q_prompt,
                    label="generate_questions", azure_deployment=azure_deployment, engine=engine,
                    response_mime_type="application/json",
                )
            except (GeminiCallError, TextGenerationError) as exc:
                raise AudioToAudioError(f"Question generation failed: {exc}") from exc
            calls.append(q_result.call_record)

            q_raw = q_result.text.strip()
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
            "audio_to_audio: wrote %s (mode=%s, asr_engine=%s, target_language=%s, questions=%s, est. cost $%.6f)",
            output_path, mode, asr_engine, target_language, len(questions) if questions else 0, cost["total_usd"],
        )

        return CapabilityOutput(
            file_path=output_path,
            text=script,
            data=parsed,
            metadata={
                "mode": mode,
                "language": language,
                "target_language": target_language,
                "asr_engine": asr_engine,
                "question_model": question_model,
                "tts_model": tts_model,
                "voice": voice,
                "raw_transcript": raw_transcript,
                "cleaned_script": script,
                "duration_seconds": duration_seconds,
                "generate_questions": want_questions,
                "question_count": len(questions) if questions else 0,
                "questions_json_path": str(json_path) if json_path else None,
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
