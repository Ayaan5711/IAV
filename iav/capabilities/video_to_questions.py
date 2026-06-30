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
import os
import re
from pathlib import Path
from typing import Any

from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput
from iav.models.config import Config, load_config
from iav.models.gemini_client import GeminiCallError, GeminiClient, get_client
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
        model = os.environ.get("GEMINI_VIDEO_MODEL") or self._settings["model"]

        params = payload.params or {}
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

        parsed = _parse_json_loose(raw_text)
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

        logger.info(
            "video_to_questions: wrote %s (%d questions)",
            output_path,
            len(questions),
        )

        return CapabilityOutput(
            file_path=output_path,
            data=parsed,
            text=_questions_as_markdown(questions),
            metadata={
                "model": model,
                "input_file": str(source),
                "input_bytes": len(video_bytes),
                "question_count": len(questions),
                "params": {"count": count, "type": qtype, "level": level},
                "mime_type": "application/json",
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


def _parse_json_loose(raw: str) -> Any:
    """Parse JSON, tolerating a model that wrapped the output in a code fence."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strip ```json ... ``` fences if present.
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", raw, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # Last-ditch: grab the outermost {...} block.
    brace = re.search(r"\{.*\}", raw, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(0))
        except json.JSONDecodeError:
            pass

    raise VideoToQuestionsError(
        "Could not parse the model output as JSON. First 400 chars: "
        f"{raw[:400]}"
    )


def _questions_as_markdown(questions: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for i, q in enumerate(questions, start=1):
        stem = q.get("stem") or q.get("question") or "(no stem)"
        lines.append(f"**Q{i}.** {stem}")
        opts = q.get("options")
        if isinstance(opts, list) and opts:
            for j, opt in enumerate(opts):
                letter = chr(ord("A") + j)
                lines.append(f"  - {letter}. {opt}")
        ans = q.get("answer")
        if ans is not None:
            lines.append(f"**Answer:** {ans}")
        expl = q.get("explanation")
        if expl:
            lines.append(f"_Explanation:_ {expl}")
        ts = q.get("timestamp")
        if ts:
            lines.append(f"_Timestamp:_ `{ts}`")
        lines.append("")
    return "\n".join(lines)
