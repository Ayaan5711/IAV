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
import os
import wave
from typing import Any

from iav.capabilities._json_utils import JsonParseError, parse_json_loose, questions_as_markdown
from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput
from iav.models.config import Config, load_config
from iav.models.gemini_client import GeminiCallError, GeminiClient, get_client
from iav.models.pricing import summarize_costs
from iav.storage import save_output

logger = logging.getLogger(__name__)


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
                "AudioQuestionGeneration requires text input (a topic or a passage)."
            )

        text_model = os.environ.get("GEMINI_TEXT_MODEL") or self._settings["text_model"]
        tts_model = os.environ.get("GEMINI_TTS_MODEL") or self._settings["tts_model"]
        voice = self._settings.get("voice_preset", "Kore")
        sample_rate = int(self._settings.get("sample_rate_hz", 24000))

        params = payload.params or {}
        mode = params.get("mode", "topic")  # "topic" | "passage"
        count = int(params.get("count", self._settings.get("default_question_count", 5)))
        qtype = params.get("type") or self._settings.get("default_question_type", "mcq")
        level = params.get("level") or self._settings.get("default_level", "undergraduate")

        calls: list[dict[str, Any]] = []

        # 1. Resolve the passage ---------------------------------------------
        if mode == "passage":
            passage = raw_text
        else:
            word_count = int(self._settings.get("passage_word_count", 150))
            prompt = self._settings["passage_instruction"].format(
                topic=raw_text, word_count=word_count
            )
            logger.info("audio_question_generation: writing passage on topic=%r", raw_text)
            try:
                passage_result = self.client.generate_text(model=text_model, prompt=prompt)
            except GeminiCallError as exc:
                raise AudioQuestionGenerationError(f"Passage generation failed: {exc}") from exc
            calls.append({"label": "write_passage", "model": text_model, "usage": passage_result.usage})
            passage = (passage_result.text or "").strip()
            if not passage:
                raise AudioQuestionGenerationError("Model returned no passage text.")

        # 2. Narrate the passage ----------------------------------------------
        instruction = (payload.instruction or "").strip() or None
        logger.info(
            "audio_question_generation: synthesising narration, chars=%d", len(passage)
        )
        try:
            tts_result = self.client.synthesize_speech(
                model=tts_model,
                script=passage,
                voice_preset=voice,
                instruction=instruction,
            )
        except GeminiCallError as exc:
            raise AudioQuestionGenerationError(f"TTS call failed: {exc}") from exc
        calls.append({"label": "narrate", "model": tts_model, "usage": tts_result.usage})
        if not tts_result.audio_bytes:
            note = (tts_result.text or "").strip() or "(no detail)"
            raise AudioQuestionGenerationError(f"TTS returned no audio. Model said: {note}")

        wav_bytes = _wrap_pcm_as_wav(tts_result.audio_bytes, sample_rate=sample_rate)
        audio_path = save_output(data=wav_bytes, suffix=".wav", capability=self.name)

        # 3. Generate questions from the passage -------------------------------
        q_prompt = self._settings["questions_instruction"].format(
            count=count, question_type=qtype, level=level, passage=passage
        )
        logger.info("audio_question_generation: generating questions")
        try:
            q_result = self.client.generate_text(
                model=text_model, prompt=q_prompt, response_mime_type="application/json"
            )
        except GeminiCallError as exc:
            raise AudioQuestionGenerationError(f"Question generation failed: {exc}") from exc
        calls.append({"label": "generate_questions", "model": text_model, "usage": q_result.usage})

        q_raw = (q_result.text or "").strip()
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
                "questions_json_path": str(json_path),
                "text_model": text_model,
                "tts_model": tts_model,
                "voice": voice,
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
