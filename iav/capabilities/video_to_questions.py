"""Video → Questions.

Uses Gemini's video-understanding capability to produce a structured
question/answer set from a source video. Output is JSON with a fixed
schema (see config.yaml -> video_to_questions.default_instruction).

POC scope: short videos passed inline as bytes. Long videos (over the
inline size limit) will need the Files API or GCS handoff — a follow-up.
"""

from __future__ import annotations

import json
import logging
import mimetypes
from pathlib import Path

from iav.capabilities._json_utils import JsonParseError, parse_json_loose, questions_as_markdown
from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput
from iav.models.config import Config, load_config
from iav.models.gemini_client import GeminiCallError, GeminiClient, get_client
from iav.models.pricing import summarize_costs
from iav.storage import save_output

logger = logging.getLogger(__name__)


class VideoToQuestionsError(RuntimeError):
    """Raised when question generation cannot produce a usable result."""


class VideoToQuestions(Capability):
    name = "video_to_questions"

    def __init__(self, client: GeminiClient | None = None, config: Config | None = None):
        self.config = config or load_config()
        self.client = client or get_client(self.config)
        self._settings = self.config.capability(self.name)

    def process(self, payload: CapabilityInput) -> CapabilityOutput:
        if payload.file_path is None:
            raise ValueError("VideoToQuestions requires an input video file path")

        source = Path(payload.file_path)
        if not source.exists():
            raise FileNotFoundError(f"Input video not found: {source}")

        video_bytes = source.read_bytes()
        mime_type = _guess_video_mime(source)
        params = payload.params or {}
        model = params.get("model") or self._settings["model"]
        count = int(params.get("count", self._settings.get("default_question_count", 5)))
        qtype = params.get("type") or self._settings.get("default_question_type", "mcq")
        level = params.get("level") or self._settings.get("default_level", "undergraduate")

        # User-supplied instruction overrides everything; otherwise format the
        # default template with the chosen count/type/level.
        user_instruction = (payload.instruction or "").strip()
        if user_instruction:
            instruction = user_instruction
        else:
            instruction = self._settings["default_instruction"].format(
                count=count,
                question_type=qtype,
                level=level,
            )

        logger.info(
            "video_to_questions: model=%s file=%s (%d bytes) count=%d type=%s level=%s",
            model,
            source.name,
            len(video_bytes),
            count,
            qtype,
            level,
        )

        try:
            result = self.client.understand_video(
                model=model,
                video_bytes=video_bytes,
                video_mime_type=mime_type,
                instruction=instruction,
                response_mime_type="application/json",
            )
        except GeminiCallError as exc:
            raise VideoToQuestionsError(f"Gemini call failed: {exc}") from exc

        raw_text = (result.text or "").strip()
        if not raw_text:
            raise VideoToQuestionsError(
                "Model returned no text. The video may have been blocked by a "
                "safety filter, or it exceeds the inline size limit."
            )

        try:
            parsed = parse_json_loose(raw_text)
        except JsonParseError as exc:
            raise VideoToQuestionsError(str(exc)) from exc
        if not isinstance(parsed, dict) or "questions" not in parsed:
            raise VideoToQuestionsError(
                "Model returned content that did not match the questions schema. "
                f"First 400 chars of output: {raw_text[:400]}"
            )

        questions = parsed.get("questions") or []
        if not isinstance(questions, list) or not questions:
            raise VideoToQuestionsError("Model returned an empty 'questions' list.")

        # Persist the full JSON next to the source video for traceability.
        json_bytes = json.dumps(parsed, indent=2, ensure_ascii=False).encode("utf-8")
        output_path = save_output(
            data=json_bytes,
            suffix=".json",
            capability=self.name,
        )

        cost = summarize_costs(
            [{"label": "video_understanding", "model": model, "usage": result.usage}],
            self.config.pricing,
        )

        logger.info(
            "video_to_questions: wrote %s (%d questions, est. cost $%.6f)",
            output_path,
            len(questions),
            cost["total_usd"],
        )

        return CapabilityOutput(
            file_path=output_path,
            data=parsed,
            text=questions_as_markdown(questions),
            metadata={
                "model": model,
                "input_file": str(source),
                "input_bytes": len(video_bytes),
                "question_count": len(questions),
                "params": {"count": count, "type": qtype, "level": level},
                "mime_type": "application/json",
                "cost": cost,
            },
        )


def _guess_video_mime(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed and guessed.startswith("video/"):
        return guessed
    suffix = path.suffix.lower().lstrip(".")
    fallback = {
        "mp4": "video/mp4",
        "mov": "video/quicktime",
        "webm": "video/webm",
        "mkv": "video/x-matroska",
        "avi": "video/x-msvideo",
    }
    if suffix in fallback:
        return fallback[suffix]
    raise ValueError(f"Unsupported video format: {path.suffix}")
