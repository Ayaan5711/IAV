"""Topic/passage → narrated audio + comprehension questions.

Two input modes:
  - topic:   a short phrase. Gemini writes an educational passage on it.
  - passage: the user supplies the full passage/script text directly.

Pipeline: passage text -> TTS narration (audio)
                        -> question generation (JSON, from the same passage)

Output questions are text (read on screen), not narrated — the audio only
carries the passage itself, matching a listening-comprehension worksheet
format rather than a fully spoken quiz.
"""

from __future__ import annotations

import io
import json
import logging
import wave
from typing import Any

from iav.capabilities._json_utils import JsonParseError, parse_json_loose, questions_as_markdown
from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput
from iav.models import audio_generation
from iav.models.config import Config, load_config
from iav.models.gemini_client import GeminiCallError, GeminiClient, get_client
from iav.models.pricing import summarize_costs
from iav.models.text_generation import TextGenerationError, generate_text, translate_text
from iav.storage import save_output

logger = logging.getLogger(__name__)

_MULTI_SPEAKER_VOICES = ["Kore", "Puck"]


class AudioQuestionGenerationError(RuntimeError):
    """Raised when the topic/passage -> audio+questions pipeline fails."""


class AudioQuestionGeneration(Capability):
    name = "audio_question_generation"

    def __init__(self, client: GeminiClient | None = None, config: Config | None = None):
        self.config = config or load_config()
        self.client = client or get_client(self.config)
        self._settings = self.config.capability(self.name)

    def process(self, payload: CapabilityInput) -> CapabilityOutput:
        raw_text = (payload.text or "").strip()
        if not raw_text:
            raise ValueError(
                "AudioQuestionGeneration requires text input (a topic/scenario or a passage)."
            )

        params = payload.params or {}
        text_model = params.get("text_model") or self._settings["text_model"]
        tts_model = params.get("tts_model") or self._settings["tts_model"]
        voice = params.get("voice") or self._settings.get("voice_preset", "Kore")
        sample_rate = int(self._settings.get("sample_rate_hz", 24000))

        mode = params.get("mode", "topic")  # "topic" | "passage"
        count = int(params.get("count", self._settings.get("default_question_count", 5)))
        qtype = params.get("type") or self._settings.get("default_question_type", "mcq")
        level = params.get("level") or self._settings.get("default_level", "undergraduate")
        length = params.get("length") or self._settings["lengths"][0]
        accent = params.get("accent") or self._settings["accents"][0]
        speed = params.get("speed") or self._settings["speeds"][0]
        tone = params.get("tone") or self._settings["tones"][0]
        multi_speaker = bool(params.get("multi_speaker", False))
        azure_deployment = self.config.azure_openai.get("default_deployment")
        engine = params.get("engine", "auto")
        azure_voice = self._settings.get("azure_voice")
        tts_engine = params.get("tts_engine", "auto")
        target_language = params.get("target_language") or self.config.languages.get(
            "default_output_language", "Same as input"
        )

        calls: list[dict[str, Any]] = []

        # 1. Resolve the passage ---------------------------------------------
        if mode == "passage":
            passage = raw_text
        else:
            word_count = self._settings.get("length_word_counts", {}).get(length, 150)
            prompt = self._settings["passage_instruction"].format(
                topic=raw_text, word_count=word_count
            )
            logger.info("audio_question_generation: writing passage on topic/scenario=%r", raw_text)
            try:
                passage_result = generate_text(
                    gemini_client=self.client, gemini_model=text_model, prompt=prompt,
                    label="write_passage", azure_deployment=azure_deployment, engine=engine,
                )
            except (GeminiCallError, TextGenerationError) as exc:
                raise AudioQuestionGenerationError(f"Passage generation failed: {exc}") from exc
            calls.append(passage_result.call_record)
            passage = passage_result.text.strip()
            if not passage:
                raise AudioQuestionGenerationError("Model returned no passage text.")

        # 1b. Translate into a different output language, if requested --------
        if target_language and target_language != "Same as input":
            translate_template = self.config.languages.get("translate_instruction")
            if not translate_template:
                raise AudioQuestionGenerationError("No translate_instruction configured under languages: in config.yaml.")
            logger.info("audio_question_generation: translating passage into %s", target_language)
            try:
                translated = translate_text(
                    gemini_client=self.client, gemini_model=text_model, text=passage,
                    target_language=target_language, translate_instruction_template=translate_template,
                    azure_deployment=azure_deployment, engine=engine,
                )
            except (GeminiCallError, TextGenerationError) as exc:
                raise AudioQuestionGenerationError(f"Translation to {target_language} failed: {exc}") from exc
            calls.append(translated.call_record)
            passage = translated.text.strip() or passage

        # 2. Narrate the passage ----------------------------------------------
        narration_prompt = self._settings["narration_instruction"].format(
            tone=tone, speed=speed, accent=accent, passage=passage
        )
        speakers = None
        if multi_speaker:
            speakers = [
                {"speaker": "Speaker1", "voice": _MULTI_SPEAKER_VOICES[0]},
                {"speaker": "Speaker2", "voice": _MULTI_SPEAKER_VOICES[1]},
            ]
            narration_prompt += (
                "\n\nRender this as a two-speaker dialogue. Label each line "
                "'Speaker1:' or 'Speaker2:' before narrating it."
            )

        instruction = (payload.instruction or "").strip() or None
        logger.info(
            "audio_question_generation: synthesising narration, chars=%d, multi_speaker=%s, tts_engine=%s",
            len(narration_prompt), multi_speaker, tts_engine,
        )
        try:
            tts_result = audio_generation.synthesize_speech(
                gemini_client=self.client,
                gemini_model=tts_model,
                script=narration_prompt,
                label="narrate",
                voice_preset=None if speakers else voice,
                speakers=speakers,
                instruction=instruction,
                azure_voice=azure_voice,
                engine=tts_engine,
            )
        except audio_generation.AudioSynthesisError as exc:
            raise AudioQuestionGenerationError(str(exc)) from exc
        calls.append(tts_result.call_record)

        if tts_result.is_raw_pcm:
            wav_bytes = _wrap_pcm_as_wav(tts_result.audio_bytes, sample_rate=sample_rate)
            duration_seconds = _pcm_duration_seconds(tts_result.audio_bytes, sample_rate=sample_rate)
        else:
            wav_bytes = tts_result.audio_bytes
            duration_seconds = audio_generation.wav_duration_seconds(wav_bytes)
        audio_path = save_output(data=wav_bytes, suffix=".wav", capability=self.name)

        # 3. Generate questions from the passage -------------------------------
        q_prompt = self._settings["questions_instruction"].format(
            count=count, question_type=qtype, level=level, passage=passage
        )
        logger.info("audio_question_generation: generating questions")
        try:
            q_result = generate_text(
                gemini_client=self.client, gemini_model=text_model, prompt=q_prompt,
                label="generate_questions", azure_deployment=azure_deployment, engine=engine,
                response_mime_type="application/json",
            )
        except (GeminiCallError, TextGenerationError) as exc:
            raise AudioQuestionGenerationError(f"Question generation failed: {exc}") from exc
        calls.append(q_result.call_record)

        q_raw = q_result.text.strip()
        if not q_raw:
            raise AudioQuestionGenerationError("Model returned no question text.")
        try:
            parsed = parse_json_loose(q_raw)
        except JsonParseError as exc:
            raise AudioQuestionGenerationError(str(exc)) from exc

        questions = parsed.get("questions") if isinstance(parsed, dict) else None
        if not isinstance(questions, list) or not questions:
            raise AudioQuestionGenerationError("Model returned no usable questions.")

        json_bytes = json.dumps(parsed, indent=2, ensure_ascii=False).encode("utf-8")
        json_path = save_output(
            data=json_bytes, suffix=".json", capability=f"{self.name}-questions"
        )

        cost = summarize_costs(calls, self.config.pricing)

        logger.info(
            "audio_question_generation: wrote %s + %s (%d questions, est. cost $%.6f)",
            audio_path,
            json_path,
            len(questions),
            cost["total_usd"],
        )

        return CapabilityOutput(
            file_path=audio_path,
            text=questions_as_markdown(questions),
            data=parsed,
            metadata={
                "mode": mode,
                "passage": passage,
                "target_language": target_language,
                "questions_json_path": str(json_path),
                "text_model": text_model,
                "tts_model": tts_model,
                "voice": voice,
                "tts_engine": tts_result.engine,
                "multi_speaker": multi_speaker,
                "accent": accent,
                "speed": speed,
                "tone": tone,
                "length": length,
                "duration_seconds": duration_seconds,
                "question_count": len(questions),
                "params": {"count": count, "type": qtype, "level": level},
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


def _pcm_duration_seconds(pcm_bytes: bytes, *, sample_rate: int, channels: int = 1, sample_width: int = 2) -> float:
    if sample_rate <= 0:
        return 0.0
    return len(pcm_bytes) / (sample_rate * channels * sample_width)
