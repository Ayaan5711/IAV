"""Azure OpenAI wrapper — primary text-generation engine, Gemini is the fallback.

Optional dependency: if the `openai` package isn't installed, or
AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY aren't set, every function here
raises AzureOpenAIUnavailable rather than crashing the app. Callers (see
iav/models/text_generation.py) catch that and fall back to Gemini.
"""

from __future__ import annotations

import base64
import io
import logging
import os
from dataclasses import dataclass
from typing import Any

import requests

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


@dataclass
class AzureImageResult:
    image_bytes: bytes
    mime_type: str = "image/png"
    # DALL-E-3 silently rewrites prompts via its own internal model before
    # generating -- this is what it actually rendered, when Azure reports
    # it (gpt-image-1 generally doesn't rewrite, so this is usually None
    # there). Surface it to the caller rather than let the rewrite happen
    # invisibly.
    revised_prompt: str | None = None


# DALL-E-3's documented prompt limit; gpt-image-1 allows quite a lot more,
# but a deployment name doesn't reliably tell us which model it actually
# runs, so this errs conservative rather than risk a cryptic 400 from Azure.
MAX_IMAGE_PROMPT_CHARS = 4000


_client_singleton = None


def is_configured() -> bool:
    if not _SDK_AVAILABLE:
        logger.info("azure_openai: not configured -- the 'openai' package is not installed")
        return False
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    key = os.environ.get("AZURE_OPENAI_API_KEY")
    if not endpoint or not key:
        logger.info(
            "azure_openai: not configured -- AZURE_OPENAI_ENDPOINT=%s, AZURE_OPENAI_API_KEY=%s",
            "set" if endpoint else "MISSING", "set" if key else "MISSING",
        )
        return False
    return True


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


def _decode_image_response(response: Any, *, label: str) -> tuple[bytes, str | None]:
    item = response.data[0] if getattr(response, "data", None) else None
    if item is None:
        raise AzureOpenAIUnavailable(f"Azure OpenAI {label} returned no image data.")
    revised_prompt = getattr(item, "revised_prompt", None)
    b64 = getattr(item, "b64_json", None)
    if b64:
        return base64.b64decode(b64), revised_prompt
    url = getattr(item, "url", None)
    if url:
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise AzureOpenAIUnavailable(f"Could not download Azure OpenAI {label} result: {exc}") from exc
        return resp.content, revised_prompt
    raise AzureOpenAIUnavailable(f"Azure OpenAI {label} response had neither b64_json nor url.")


def generate_image(
    prompt: str, *, deployment: str, size: str = "1024x1024", quality: str = "standard"
) -> AzureImageResult:
    """Text-to-image via Azure OpenAI's Images API (DALL-E-3 / gpt-image-1
    deployments). Azure images bill a flat rate per image, not per token --
    no usage/token counts come back from this endpoint.
    """
    if not _SDK_AVAILABLE:
        raise AzureOpenAIUnavailable("The 'openai' package is not installed.")
    if not is_configured():
        raise AzureOpenAIUnavailable("AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY are not set.")
    if len(prompt) > MAX_IMAGE_PROMPT_CHARS:
        raise AzureOpenAIUnavailable(
            f"Prompt is {len(prompt)} characters, over the {MAX_IMAGE_PROMPT_CHARS}-character "
            "limit Azure's Images API enforces for DALL-E-3 (gpt-image-1 deployments allow more, "
            "but this check errs conservative since the deployment's actual model isn't known "
            "here). Shorten the description or the assessment-metadata block."
        )

    client = _get_client()
    logger.info("azure_openai: generating image (deployment=%s, size=%s)", deployment, size)
    try:
        response = client.images.generate(model=deployment, prompt=prompt, size=size, quality=quality, n=1)
    except Exception as exc:
        logger.exception("azure_openai: image generation failed (deployment=%s)", deployment)
        raise AzureOpenAIUnavailable(str(exc)) from exc

    image_bytes, revised_prompt = _decode_image_response(response, label="image generation")
    logger.info("azure_openai: image generated (%d bytes)", len(image_bytes))
    if revised_prompt and revised_prompt != prompt:
        logger.info("azure_openai: DALL-E-3 rewrote the prompt before generating -- see revised_prompt")
    return AzureImageResult(image_bytes=image_bytes, revised_prompt=revised_prompt)


def edit_image(
    prompt: str,
    *,
    deployment: str,
    image_bytes: bytes,
    image_mime_type: str = "image/png",
    size: str = "1024x1024",
) -> AzureImageResult:
    """Image-in/image-out edit via Azure OpenAI's Images API.

    Only gpt-image-1 deployments support editing on Azure -- dall-e-3
    doesn't expose an edit endpoint, so this will fail against a dall-e-3
    deployment even though generate_image() works fine against the same one.
    """
    if not _SDK_AVAILABLE:
        raise AzureOpenAIUnavailable("The 'openai' package is not installed.")
    if not is_configured():
        raise AzureOpenAIUnavailable("AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY are not set.")
    if len(prompt) > MAX_IMAGE_PROMPT_CHARS:
        raise AzureOpenAIUnavailable(
            f"Prompt is {len(prompt)} characters, over the {MAX_IMAGE_PROMPT_CHARS}-character "
            "limit Azure's Images API enforces for DALL-E-3 (gpt-image-1 deployments allow more, "
            "but this check errs conservative since the deployment's actual model isn't known "
            "here). Shorten the instruction text."
        )

    client = _get_client()
    ext = "jpg" if "jpeg" in image_mime_type else "png"
    buf = io.BytesIO(image_bytes)
    buf.name = f"image.{ext}"  # the SDK needs a filename to set the multipart content-type

    logger.info("azure_openai: editing image (deployment=%s, size=%s)", deployment, size)
    try:
        response = client.images.edit(model=deployment, image=buf, prompt=prompt, size=size, n=1)
    except Exception as exc:
        logger.exception("azure_openai: image edit failed (deployment=%s)", deployment)
        raise AzureOpenAIUnavailable(str(exc)) from exc

    image_bytes_out, revised_prompt = _decode_image_response(response, label="image edit")
    logger.info("azure_openai: image edited (%d bytes)", len(image_bytes_out))
    return AzureImageResult(image_bytes=image_bytes_out, revised_prompt=revised_prompt)
