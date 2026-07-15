"""Generate Image — structured prompt → new exam-question image.

Unlike image_enhance (which edits an SME's existing sketch), this generates
an image from nothing: assessment metadata + media-specific attributes
assembled into one prompt, sent straight to Nano Banana with no input image.
"""

from __future__ import annotations

import json
import logging

from iav.capabilities._json_utils import JsonParseError, parse_json_loose
from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput
from iav.capabilities.prompt_schema import (
    CommonAttributes,
    common_block,
    validate_common_attributes,
    validate_free_text,
)
from iav.models import image_generation
from iav.models.config import Config, load_config
from iav.models.gemini_client import GeminiCallError, GeminiClient, get_client
from iav.models.pricing import summarize_costs
from iav.storage import save_output

logger = logging.getLogger(__name__)


class ImageGenerateError(RuntimeError):
    """Raised when image generation cannot produce an output."""


def _format_label_scheme_for_render(labels: list[dict]) -> str:
    """One line per label, worded for the *image* model -- placeholders need
    their concept described so the model knows where/how to draw the tag,
    while being told explicitly never to print that concept as text.
    """
    lines = []
    for item in labels:
        lid = item.get("id", "?")
        if item.get("kind") == "given":
            lines.append(f'- {lid}: GIVEN -- render exactly as "{item.get("value", "")}"')
        else:
            lines.append(
                f'- {lid}: PLACEHOLDER -- this part represents "{item.get("concept", "")}" '
                f'(render ONLY the bare id "{lid}" here; never print the concept text)'
            )
    return "\n".join(lines)


def _format_placeholder_scheme_for_questions(labels: list[dict]) -> str:
    """Placeholder entries only, worded as an answer key for the *question*
    model -- it never sees the image, so there's nothing left to re-guess.
    """
    return "\n".join(
        f'- {item.get("id", "?")}: {item.get("concept", "")}'
        for item in labels
        if item.get("kind") == "placeholder"
    )


class ImageGenerate(Capability):
    name = "image_generate"

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
        visual_type = params.get("visual_type") or self._settings["visual_types"][0]
        style = params.get("style") or self._settings["styles"][0]

        errors = validate_common_attributes(common) + validate_free_text(free_text)
        if errors:
            raise ValueError("; ".join(errors))

        model = params.get("model") or self._settings["model"]
        resolution = params.get("resolution") or self._settings.get("resolution")
        output_format = params.get("output_format") or self._settings.get("output_format")
        want_questions = bool(params.get("generate_questions", False))
        question_model = params.get("question_model") or self._settings.get("question_model", model)
        count = int(params.get("count", self._settings.get("default_question_count", 5)))
        qtype = params.get("type") or self._settings.get("default_question_type", "mcq")
        level = params.get("level") or self._settings.get("default_level", "undergraduate")
        use_label_placeholders = bool(params.get("use_label_placeholders", False))
        prompt = self._settings["prompt_template"].format(
            visual_type=visual_type,
            style=style,
            common_block=common_block(common),
            free_text=free_text,
        )

        calls: list[dict] = []
        labels: list[dict] | None = None
        label_json_path = None

        if use_label_placeholders:
            design_prompt = self._settings["label_design_instruction"].format(free_text=free_text)
            logger.info("image_generate: designing label scheme before rendering")
            try:
                design_result = self.client.generate_text(
                    model=question_model, prompt=design_prompt, response_mime_type="application/json",
                )
            except GeminiCallError as exc:
                raise ImageGenerateError(f"Label design failed: {exc}") from exc
            calls.append({"label": "design_labels", "model": question_model, "usage": design_result.usage})

            design_raw = (design_result.text or "").strip()
            if not design_raw:
                raise ImageGenerateError("Label design returned no text.")
            try:
                design_parsed = parse_json_loose(design_raw)
            except JsonParseError as exc:
                raise ImageGenerateError(str(exc)) from exc

            labels = design_parsed.get("labels") if isinstance(design_parsed, dict) else None
            if not isinstance(labels, list) or not labels:
                raise ImageGenerateError("Label design returned no usable labels.")

            prompt = prompt + "\n\n" + self._settings["label_render_instruction"].format(
                label_summary=_format_label_scheme_for_render(labels)
            )
            label_bytes = json.dumps({"labels": labels}, indent=2, ensure_ascii=False).encode("utf-8")
            label_json_path = save_output(data=label_bytes, suffix=".json", capability=f"{self.name}-labels")

        azure_image_deployment = self.config.azure_openai.get("image_deployment")
        image_engine = params.get("image_engine", "auto")

        logger.info(
            "image_generate: model=%s visual_type=%s style=%s resolution=%s label_placeholders=%s image_engine=%s",
            model, visual_type, style, resolution, use_label_placeholders, image_engine,
        )

        try:
            result = image_generation.generate_image(
                gemini_client=self.client,
                gemini_model=model,
                prompt=prompt,
                label="image_generate",
                resolution=resolution,
                output_mime_type=output_format,
                azure_deployment=azure_image_deployment,
                engine=image_engine,
            )
        except image_generation.ImageGenerationError as exc:
            raise ImageGenerateError(
                f"{exc} (a Gemini failure here typically means a safety filter blocked the output)"
            ) from exc

        image_mime_type = result.image_mime_type
        suffix = ".jpg" if image_mime_type == "image/jpeg" else ".png"
        output_path = save_output(data=result.image_bytes, suffix=suffix, capability=self.name)

        calls.append(result.call_record)

        questions: list | None = None
        parsed: dict | None = None
        json_path = None
        if want_questions:
            # Placeholder entries carry their own answer key -- grounding the
            # question call in that key (no image bytes needed) instead of
            # having it re-derive labels by looking at the rendered picture,
            # which is what caused duplicate/mismatched labels before.
            placeholder_entries = [item for item in labels if item.get("kind") == "placeholder"] if labels else []
            if placeholder_entries:
                q_prompt = self._settings["placeholder_questions_instruction"].format(
                    question_type=qtype,
                    placeholder_summary=_format_placeholder_scheme_for_questions(labels),
                )
                logger.info(
                    "image_generate: generating questions from the label answer key (%d placeholders)",
                    len(placeholder_entries),
                )
                try:
                    q_result = self.client.generate_text(
                        model=question_model, prompt=q_prompt, response_mime_type="application/json",
                    )
                except GeminiCallError as exc:
                    raise ImageGenerateError(f"Question generation failed: {exc}") from exc
            else:
                q_prompt = self._settings["questions_instruction"].format(count=count, question_type=qtype, level=level)
                logger.info("image_generate: generating questions from the image")
                try:
                    q_result = self.client.understand_image(
                        model=question_model, image_bytes=result.image_bytes, image_mime_type=image_mime_type,
                        instruction=q_prompt, response_mime_type="application/json",
                    )
                except GeminiCallError as exc:
                    raise ImageGenerateError(f"Question generation failed: {exc}") from exc
            calls.append({"label": "generate_questions", "model": question_model, "usage": q_result.usage})

            q_raw = (q_result.text or "").strip()
            if not q_raw:
                raise ImageGenerateError("Model returned no question text.")
            try:
                parsed = parse_json_loose(q_raw)
            except JsonParseError as exc:
                raise ImageGenerateError(str(exc)) from exc

            questions = parsed.get("questions") if isinstance(parsed, dict) else None
            if not isinstance(questions, list) or not questions:
                raise ImageGenerateError("Model returned no usable questions.")

            json_bytes = json.dumps(parsed, indent=2, ensure_ascii=False).encode("utf-8")
            json_path = save_output(data=json_bytes, suffix=".json", capability=f"{self.name}-questions")

        cost = summarize_costs(calls, self.config.pricing)

        logger.info("image_generate: wrote %s, est. cost $%.6f", output_path, cost["total_usd"])

        return CapabilityOutput(
            file_path=output_path,
            text="",
            data=parsed,
            metadata={
                "model": model,
                "image_engine": result.engine,
                "revised_prompt": result.revised_prompt,
                "visual_type": visual_type,
                "style": style,
                "prompt": prompt,
                "output_bytes": len(result.image_bytes),
                "mime_type": image_mime_type,
                "generate_questions": want_questions,
                "question_count": len(questions) if questions else 0,
                "questions_json_path": str(json_path) if json_path else None,
                "use_label_placeholders": use_label_placeholders,
                "label_count": len(labels) if labels else 0,
                "label_json_path": str(label_json_path) if label_json_path else None,
                "cost": cost,
            },
        )
