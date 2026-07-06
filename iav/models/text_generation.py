"""Text generation with a choice of engine: Azure OpenAI, Gemini, or both.

Used by every capability step that is pure text-in/text-out -- narration
scripts, transcript cleanup, passage/question writing. Capabilities that need
Gemini's multimodal understanding (video, image) don't go through this; Azure
OpenAI's chat-completions deployment never sees that input, so those calls
stay directly on GeminiClient.

Three engine modes, chosen per call (typically from a UI dropdown):
  auto:   Azure OpenAI first if configured, Gemini as an automatic fallback.
  gemini: Gemini only -- Azure is never attempted.
  azure:  Azure OpenAI only -- no fallback; fails loudly if unavailable,
          since the caller explicitly asked for it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from iav.models import azure_openai_client
from iav.models.gemini_client import GeminiClient
from iav.models.pricing import UsageInfo

logger = logging.getLogger(__name__)


class TextGenerationError(RuntimeError):
    """Raised when the explicitly-selected text-generation engine fails."""


@dataclass
class TextGenerationResult:
    text: str
    engine: str  # "azure-openai" | "gemini"
    call_record: dict[str, Any]  # ready to append to a capability's `calls` list


def _call_azure(prompt: str, *, label: str, deployment: str, response_mime_type: str | None) -> TextGenerationResult:
    azure_result = azure_openai_client.generate_text(prompt, deployment=deployment, response_mime_type=response_mime_type)
    usage = UsageInfo(
        prompt_tokens=azure_result.prompt_tokens,
        output_tokens=azure_result.completion_tokens,
        total_tokens=azure_result.total_tokens,
    )
    return TextGenerationResult(
        text=azure_result.text,
        engine="azure-openai",
        call_record={"label": label, "model": deployment, "usage": usage},
    )


def _call_gemini(
    gemini_client: GeminiClient, prompt: str, *, label: str, model: str, response_mime_type: str | None
) -> TextGenerationResult:
    result = gemini_client.generate_text(model=model, prompt=prompt, response_mime_type=response_mime_type)
    return TextGenerationResult(
        text=result.text or "",
        engine="gemini",
        call_record={"label": label, "model": model, "usage": result.usage},
    )


def generate_text(
    *,
    gemini_client: GeminiClient,
    gemini_model: str,
    prompt: str,
    label: str,
    azure_deployment: str | None = None,
    response_mime_type: str | None = None,
    engine: str = "auto",
) -> TextGenerationResult:
    engine = (engine or "auto").lower()

    if engine == "gemini":
        return _call_gemini(gemini_client, prompt, label=label, model=gemini_model, response_mime_type=response_mime_type)

    if engine == "azure":
        if not azure_deployment:
            raise TextGenerationError(f"Azure OpenAI was selected for '{label}' but no deployment is configured.")
        try:
            return _call_azure(prompt, label=label, deployment=azure_deployment, response_mime_type=response_mime_type)
        except azure_openai_client.AzureOpenAIUnavailable as exc:
            raise TextGenerationError(f"Azure OpenAI call failed for '{label}': {exc}") from exc

    # auto: Azure primary, Gemini fallback -- never hard-fails just because
    # Azure isn't configured or a call to it fails.
    attempted_azure = bool(azure_deployment) and azure_openai_client.is_configured()
    if attempted_azure:
        try:
            return _call_azure(prompt, label=label, deployment=azure_deployment, response_mime_type=response_mime_type)
        except azure_openai_client.AzureOpenAIUnavailable as exc:
            logger.warning("Azure OpenAI failed for '%s', falling back to Gemini: %s", label, exc)

    fallback_label = f"{label} (Gemini fallback)" if attempted_azure else label
    return _call_gemini(gemini_client, prompt, label=fallback_label, model=gemini_model, response_mime_type=response_mime_type)
