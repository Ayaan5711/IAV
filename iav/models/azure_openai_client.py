"""Azure OpenAI wrapper — primary text-generation engine, Gemini is the fallback.

Optional dependency: if the `openai` package isn't installed, or
AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY aren't set, every function here
raises AzureOpenAIUnavailable rather than crashing the app. Callers (see
iav/models/text_generation.py) catch that and fall back to Gemini.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    from openai import AzureOpenAI
    _SDK_AVAILABLE = True
except ImportError:
    AzureOpenAI = None  # type: ignore[assignment, misc]
    _SDK_AVAILABLE = False

DEFAULT_API_VERSION = "2024-10-21"


class AzureOpenAIUnavailable(RuntimeError):
    """Raised when Azure OpenAI can't be used -- caller should fall back."""


@dataclass
class AzureTextResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


_client_singleton = None


def is_configured() -> bool:
    return _SDK_AVAILABLE and bool(os.environ.get("AZURE_OPENAI_ENDPOINT")) and bool(os.environ.get("AZURE_OPENAI_API_KEY"))


def _get_client() -> "AzureOpenAI":
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", DEFAULT_API_VERSION),
        )
    return _client_singleton


def generate_text(prompt: str, *, deployment: str, response_mime_type: str | None = None) -> AzureTextResult:
    if not _SDK_AVAILABLE:
        raise AzureOpenAIUnavailable("The 'openai' package is not installed.")
    if not is_configured():
        raise AzureOpenAIUnavailable("AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY are not set.")

    client = _get_client()
    kwargs: dict = {}
    if response_mime_type == "application/json":
        kwargs["response_format"] = {"type": "json_object"}

    logger.info("azure_openai: generating text (deployment=%s, prompt_chars=%d)", deployment, len(prompt))
    try:
        response = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
    except Exception as exc:
        logger.exception("azure_openai: call failed (deployment=%s)", deployment)
        raise AzureOpenAIUnavailable(str(exc)) from exc

    choice = response.choices[0] if response.choices else None
    text = (choice.message.content or "").strip() if choice and choice.message else ""
    usage = response.usage

    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
    logger.info(
        "azure_openai: response usage prompt=%d completion=%d total=%d",
        prompt_tokens, completion_tokens, total_tokens,
    )

    if not text:
        raise AzureOpenAIUnavailable("Azure OpenAI returned no text (empty choice or content filtered).")

    return AzureTextResult(
        text=text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )
