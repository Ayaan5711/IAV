"""Generate Image — structured prompt → new exam-question image.

Unlike image_enhance (which edits an SME's existing sketch), this generates
an image from nothing: assessment metadata + media-specific attributes
assembled into one prompt, sent straight to Nano Banana with no input image.
"""

from __future__ import annotations

import logging

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


class ImageGenerateError(RuntimeError):
    """Raised when image generation cannot produce an output."""


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
        prompt = self._settings["prompt_template"].format(
            visual_type=visual_type,
            style=style,
            common_block=common_block(common),
            free_text=free_text,
        )

        logger.info(
            "image_generate: model=%s visual_type=%s style=%s resolution=%s",
            model, visual_type, style, resolution,
        )

        try:
            result = self.client.generate_image(
                model=model, prompt=prompt, resolution=resolution, output_mime_type=output_format
            )
        except GeminiCallError as exc:
            raise ImageGenerateError(f"Gemini call failed: {exc}") from exc

        if not result.image_bytes:
            note = (result.text or "").strip() or "(no detail)"
            raise ImageGenerateError(
                f"Model returned no image. This typically means a safety filter blocked the output. "
                f"Model said: {note}"
            )

        suffix = ".jpg" if (result.image_mime_type or "") == "image/jpeg" else ".png"
        output_path = save_output(data=result.image_bytes, suffix=suffix, capability=self.name)
        cost = summarize_costs(
            [{"label": "image_generate", "model": model, "usage": result.usage, "output_images": 1}],
            self.config.pricing,
        )

        logger.info("image_generate: wrote %s, est. cost $%.6f", output_path, cost["total_usd"])

        return CapabilityOutput(
            file_path=output_path,
            text=result.text,
            metadata={
                "model": model,
                "visual_type": visual_type,
                "style": style,
                "prompt": prompt,
                "output_bytes": len(result.image_bytes),
                "mime_type": result.image_mime_type or "image/png",
                "cost": cost,
            },
        )
