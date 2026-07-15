"""Image enhancement — hand-drawn diagram → professional render.

Wraps Nano Banana Pro behind the unified Capability interface. The default
instruction (in ``config.yaml``) is tuned to preserve labels, numbers, and
geometric relationships exactly — non-negotiable for exam-paper diagrams.
"""

from __future__ import annotations

import json
import logging
import mimetypes
from pathlib import Path

from iav.capabilities._json_utils import JsonParseError, parse_json_loose
from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput
from iav.models import image_generation
from iav.models.config import Config, load_config
from iav.models.gemini_client import GeminiCallError, GeminiClient, get_client
from iav.models.pricing import summarize_costs
from iav.storage import save_output

logger = logging.getLogger(__name__)


class ImageEnhanceError(RuntimeError):
    """Raised when image enhancement cannot produce an output."""


class ImageEnhance(Capability):
    name = "image_enhance"

    def __init__(self, client: GeminiClient | None = None, config: Config | None = None):
        self.config = config or load_config()
        self.client = client or get_client(self.config)
        self._settings = self.config.capability(self.name)

    def process(self, payload: CapabilityInput) -> CapabilityOutput:
        if payload.file_path is None:
            raise ValueError("ImageEnhance requires an input image file path")

        source = Path(payload.file_path)
        if not source.exists():
            raise FileNotFoundError(f"Input image not found: {source}")

        image_bytes = source.read_bytes()
        mime_type = _guess_mime(source)
        instruction = (payload.instruction or "").strip() or self._settings["default_instruction"]
        params = payload.params or {}
        model = params.get("model") or self._settings["model"]
        resolution = params.get("resolution") or self._settings.get("resolution")
        output_format = params.get("output_format") or self._settings.get("output_format")
        want_questions = bool(params.get("generate_questions", False))
        question_model = params.get("question_model") or self._settings.get("question_model", model)
        count = int(params.get("count", self._settings.get("default_question_count", 5)))
        qtype = params.get("type") or self._settings.get("default_question_type", "mcq")
        level = params.get("level") or self._settings.get("default_level", "undergraduate")
        azure_image_deployment = self.config.azure_openai.get("image_deployment")
        image_engine = params.get("image_engine", "auto")

        logger.info(
            "image_enhance: invoking model=%s resolution=%s on file=%s (%d bytes) image_engine=%s",
            model,
            resolution,
            source.name,
            len(image_bytes),
            image_engine,
        )

        try:
            result = image_generation.edit_image(
                gemini_client=self.client,
                gemini_model=model,
                image_bytes=image_bytes,
                image_mime_type=mime_type,
                instruction=instruction,
                label="image_edit",
                resolution=resolution,
                output_mime_type=output_format,
                azure_deployment=azure_image_deployment,
                engine=image_engine,
            )
        except image_generation.ImageGenerationError as exc:
            raise ImageEnhanceError(
                f"{exc} (a Gemini failure here typically means a safety filter blocked the output)"
            ) from exc

        image_mime_type = result.image_mime_type
        output_path = save_output(
            data=result.image_bytes,
            suffix=_suffix_for_mime(image_mime_type),
            capability=self.name,
        )

        calls = [result.call_record]

        questions: list | None = None
        parsed: dict | None = None
        json_path = None
        if want_questions:
            q_prompt = self._settings["questions_instruction"].format(count=count, question_type=qtype, level=level)
            logger.info("image_enhance: generating questions from the rendered image")
            try:
                q_result = self.client.understand_image(
                    model=question_model, image_bytes=result.image_bytes,
                    image_mime_type=image_mime_type or "image/png",
                    instruction=q_prompt, response_mime_type="application/json",
                )
            except GeminiCallError as exc:
                raise ImageEnhanceError(f"Question generation failed: {exc}") from exc
            calls.append({"label": "generate_questions", "model": question_model, "usage": q_result.usage})

            q_raw = (q_result.text or "").strip()
            if not q_raw:
                raise ImageEnhanceError("Model returned no question text.")
            try:
                parsed = parse_json_loose(q_raw)
            except JsonParseError as exc:
                raise ImageEnhanceError(str(exc)) from exc

            questions = parsed.get("questions") if isinstance(parsed, dict) else None
            if not isinstance(questions, list) or not questions:
                raise ImageEnhanceError("Model returned no usable questions.")

            json_bytes = json.dumps(parsed, indent=2, ensure_ascii=False).encode("utf-8")
            json_path = save_output(data=json_bytes, suffix=".json", capability=f"{self.name}-questions")

        cost = summarize_costs(calls, self.config.pricing)

        logger.info(
            "image_enhance: wrote %s (%d bytes, est. cost $%.6f)",
            output_path,
            len(result.image_bytes),
            cost["total_usd"],
        )

        return CapabilityOutput(
            file_path=output_path,
            text="",
            data=parsed,
            metadata={
                "model": model,
                "image_engine": result.engine,
                "revised_prompt": result.revised_prompt,
                "input_file": str(source),
                "input_bytes": len(image_bytes),
                "output_bytes": len(result.image_bytes),
                "mime_type": image_mime_type,
                "generate_questions": want_questions,
                "question_count": len(questions) if questions else 0,
                "questions_json_path": str(json_path) if json_path else None,
                "cost": cost,
            },
        )


def _guess_mime(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed and guessed.startswith("image/"):
        return guessed
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"jpg", "jpeg"}:
        return "image/jpeg"
    if suffix == "png":
        return "image/png"
    if suffix == "webp":
        return "image/webp"
    raise ValueError(f"Unsupported image format: {path.suffix}")


def _suffix_for_mime(mime: str | None) -> str:
    if not mime:
        return ".png"
    if mime == "image/jpeg":
        return ".jpg"
    if mime == "image/webp":
        return ".webp"
    return ".png"
