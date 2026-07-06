"""Text generation with Azure OpenAI as primary, Gemini as fallback.

Used by every capability step that is pure text-in/text-out -- narration
scripts, transcript cleanup, passage/question writing. Capabilities that need
Gemini's multimodal understanding (video, image) don't go through this; Azure
OpenAI's chat-completions deployment never sees that input, so those calls
stay directly on GeminiClient.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from iav.models import azure_openai_client
from iav.models.gemini_client import GeminiClient
from iav.models.pricing import UsageInfo

logger = logging.getLogger(__name__)


@dataclass
class TextGenerationResult:
    text: str
    engine: str  # "azure-openai" | "gemini"
    call_record: dict[str, Any]  # ready to append to a capability's `calls` list


def generate_text(
    *,
    gemini_client: GeminiClient,
    gemini_model: str,
    prompt: str,
    label: str,
    azure_deployment: str | None = None,
    response_mime_type: str | None = None,
) -> TextGenerationResult:
    """Tries Azure OpenAI first when configured, falls back to Gemini.

    Never hard-fails just because Azure isn't configured or a call to it
    fails -- Gemini's own GeminiCallError is the only thing that propagates.
    """
    attempted_azure = bool(azure_deployment) and azure_openai_client.is_configured()

    if attempted_azure:
        try:
            azure_result = azure_openai_client.generate_text(
                prompt, deployment=azure_deployment, response_mime_type=response_mime_type
            )
            usage = UsageInfo(
                prompt_tokens=azure_result.prompt_tokens,
                output_tokens=azure_result.completion_tokens,
                total_tokens=azure_result.total_tokens,
            )
            return TextGenerationResult(
                text=azure_result.text,
                engine="azure-openai",
                call_record={"label": label, "model": azure_deployment, "usage": usage},
            )
        except azure_openai_client.AzureOpenAIUnavailable as exc:
            logger.warning("Azure OpenAI failed for '%s', falling back to Gemini: %s", label, exc)

    result = gemini_client.generate_text(model=gemini_model, prompt=prompt, response_mime_type=response_mime_type)
    fallback_label = f"{label} (Gemini fallback)" if attempted_azure else label
    return TextGenerationResult(
        text=result.text or "",
        engine="gemini",
        call_record={"label": fallback_label, "model": gemini_model, "usage": result.usage},
    )
