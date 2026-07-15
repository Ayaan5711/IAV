"""Image generation with a choice of engine: Azure OpenAI, Gemini, or both.

Mirrors iav/models/text_generation.py's engine-selection pattern, applied to
the image-in/image-out and text-to-image capabilities (image_enhance,
image_generate).

Three engine modes, chosen per call (typically from a UI dropdown):
  auto:   Azure OpenAI first if configured, Gemini as an automatic fallback.
  gemini: Gemini only -- Azure is never attempted.
  azure:  Azure OpenAI only -- no fallback; fails loudly if unavailable,
          since the caller explicitly asked for it.

Azure OpenAI's Images API bills a flat rate per image, not per token, and
returns no usage_metadata -- callers should track cost via pricing.models'
per_image unit (see config.yaml), not the usual token-based estimate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from iav.models import azure_openai_client
from iav.models.gemini_client import GeminiCallError, GeminiClient

logger = logging.getLogger(__name__)


class ImageGenerationError(RuntimeError):
    """Raised when the explicitly-selected image engine fails."""


@dataclass
class ImageGenerationResult:
    image_bytes: bytes
    image_mime_type: str
    engine: str  # "azure-openai" | "gemini"
    call_record: dict[str, Any]  # ready to append to a capability's `calls` list
    # DALL-E-3 rewrites prompts internally before generating -- this is what
    # it actually used, when Azure reports it. None for Gemini (no
    # equivalent rewrite step) and usually None for gpt-image-1 too.
    revised_prompt: str | None = None


def _call_gemini_generate(
    gemini_client: GeminiClient, *, model: str, prompt: str, resolution: str | None,
    output_mime_type: str | None, label: str,
) -> ImageGenerationResult:
    result = gemini_client.generate_image(
        model=model, prompt=prompt, resolution=resolution, output_mime_type=output_mime_type,
    )
    if not result.image_bytes:
        raise GeminiCallError((result.text or "no image returned").strip() or "no image returned")
    return ImageGenerationResult(
        image_bytes=result.image_bytes,
        image_mime_type=result.image_mime_type or "image/png",
        engine="gemini",
        call_record={"label": label, "model": model, "usage": result.usage, "output_images": 1},
    )


def _call_azure_generate(*, deployment: str, prompt: str, size: str, quality: str, label: str) -> ImageGenerationResult:
    azure_result = azure_openai_client.generate_image(prompt, deployment=deployment, size=size, quality=quality)
    return ImageGenerationResult(
        image_bytes=azure_result.image_bytes,
        image_mime_type=azure_result.mime_type,
        engine="azure-openai",
        call_record={"label": label, "model": deployment, "usage": None, "output_images": 1},
        revised_prompt=azure_result.revised_prompt,
    )


def generate_image(
    *,
    gemini_client: GeminiClient,
    gemini_model: str,
    prompt: str,
    label: str,
    resolution: str | None = None,
    output_mime_type: str | None = None,
    azure_deployment: str | None = None,
    azure_size: str = "1024x1024",
    azure_quality: str = "standard",
    engine: str = "auto",
) -> ImageGenerationResult:
    engine = (engine or "auto").lower()

    if engine == "gemini":
        try:
            return _call_gemini_generate(
                gemini_client, model=gemini_model, prompt=prompt, resolution=resolution,
                output_mime_type=output_mime_type, label=label,
            )
        except GeminiCallError as exc:
            raise ImageGenerationError(f"Gemini call failed for '{label}': {exc}") from exc

    if engine == "azure":
        if not azure_deployment:
            raise ImageGenerationError(f"Azure OpenAI was selected for '{label}' but no image deployment is configured.")
        try:
            return _call_azure_generate(deployment=azure_deployment, prompt=prompt, size=azure_size, quality=azure_quality, label=label)
        except azure_openai_client.AzureOpenAIUnavailable as exc:
            raise ImageGenerationError(f"Azure OpenAI call failed for '{label}': {exc}") from exc

    # auto: Azure primary, Gemini fallback -- never hard-fails just because
    # Azure isn't configured or a call to it fails.
    attempted_azure = bool(azure_deployment) and azure_openai_client.is_configured()
    if attempted_azure:
        try:
            return _call_azure_generate(deployment=azure_deployment, prompt=prompt, size=azure_size, quality=azure_quality, label=label)
        except azure_openai_client.AzureOpenAIUnavailable as exc:
            logger.warning("Azure OpenAI image generation failed for '%s', falling back to Gemini: %s", label, exc)

    fallback_label = f"{label} (Gemini fallback)" if attempted_azure else label
    try:
        return _call_gemini_generate(
            gemini_client, model=gemini_model, prompt=prompt, resolution=resolution,
            output_mime_type=output_mime_type, label=fallback_label,
        )
    except GeminiCallError as exc:
        raise ImageGenerationError(f"Gemini call failed for '{label}': {exc}") from exc


def _call_gemini_edit(
    gemini_client: GeminiClient, *, model: str, image_bytes: bytes, image_mime_type: str,
    instruction: str, resolution: str | None, output_mime_type: str | None, label: str,
) -> ImageGenerationResult:
    result = gemini_client.edit_image(
        model=model, image_bytes=image_bytes, image_mime_type=image_mime_type, instruction=instruction,
        resolution=resolution, output_mime_type=output_mime_type,
    )
    if not result.image_bytes:
        raise GeminiCallError((result.text or "no image returned").strip() or "no image returned")
    return ImageGenerationResult(
        image_bytes=result.image_bytes,
        image_mime_type=result.image_mime_type or "image/png",
        engine="gemini",
        call_record={"label": label, "model": model, "usage": result.usage, "output_images": 1},
    )


def _call_azure_edit(*, deployment: str, image_bytes: bytes, image_mime_type: str, instruction: str, size: str, label: str) -> ImageGenerationResult:
    azure_result = azure_openai_client.edit_image(
        instruction, deployment=deployment, image_bytes=image_bytes, image_mime_type=image_mime_type, size=size,
    )
    return ImageGenerationResult(
        image_bytes=azure_result.image_bytes,
        image_mime_type=azure_result.mime_type,
        engine="azure-openai",
        call_record={"label": label, "model": deployment, "usage": None, "output_images": 1},
        revised_prompt=azure_result.revised_prompt,
    )


def edit_image(
    *,
    gemini_client: GeminiClient,
    gemini_model: str,
    image_bytes: bytes,
    image_mime_type: str,
    instruction: str,
    label: str,
    resolution: str | None = None,
    output_mime_type: str | None = None,
    azure_deployment: str | None = None,
    azure_size: str = "1024x1024",
    engine: str = "auto",
) -> ImageGenerationResult:
    engine = (engine or "auto").lower()

    if engine == "gemini":
        try:
            return _call_gemini_edit(
                gemini_client, model=gemini_model, image_bytes=image_bytes, image_mime_type=image_mime_type,
                instruction=instruction, resolution=resolution, output_mime_type=output_mime_type, label=label,
            )
        except GeminiCallError as exc:
            raise ImageGenerationError(f"Gemini call failed for '{label}': {exc}") from exc

    if engine == "azure":
        if not azure_deployment:
            raise ImageGenerationError(f"Azure OpenAI was selected for '{label}' but no image deployment is configured.")
        try:
            return _call_azure_edit(
                deployment=azure_deployment, image_bytes=image_bytes, image_mime_type=image_mime_type,
                instruction=instruction, size=azure_size, label=label,
            )
        except azure_openai_client.AzureOpenAIUnavailable as exc:
            raise ImageGenerationError(f"Azure OpenAI call failed for '{label}': {exc}") from exc

    attempted_azure = bool(azure_deployment) and azure_openai_client.is_configured()
    if attempted_azure:
        try:
            return _call_azure_edit(
                deployment=azure_deployment, image_bytes=image_bytes, image_mime_type=image_mime_type,
                instruction=instruction, size=azure_size, label=label,
            )
        except azure_openai_client.AzureOpenAIUnavailable as exc:
            logger.warning("Azure OpenAI image edit failed for '%s', falling back to Gemini: %s", label, exc)

    fallback_label = f"{label} (Gemini fallback)" if attempted_azure else label
    try:
        return _call_gemini_edit(
            gemini_client, model=gemini_model, image_bytes=image_bytes, image_mime_type=image_mime_type,
            instruction=instruction, resolution=resolution, output_mime_type=output_mime_type, label=fallback_label,
        )
    except GeminiCallError as exc:
        raise ImageGenerationError(f"Gemini call failed for '{label}': {exc}") from exc
