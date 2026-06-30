"""Vertex AI client wrapper.

Thin wrapper around the ``google-genai`` SDK configured for Vertex AI. The
rest of the codebase only ever talks to this wrapper — never to the SDK
directly — so authentication, retries, and model-ID indirection are all in
one place.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from google import genai
from google.genai import types as genai_types
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from iav.models.config import Config, load_config

logger = logging.getLogger(__name__)


class GeminiCallError(RuntimeError):
    """Raised when a Gemini call fails after retries."""


@dataclass
class GenerationResult:
    text: str | None = None
    image_bytes: bytes | None = None
    image_mime_type: str | None = None
    audio_bytes: bytes | None = None
    audio_mime_type: str | None = None
    raw: Any = None


def _ensure_credentials_visible(creds_path: Path) -> None:
    """Make sure GOOGLE_APPLICATION_CREDENTIALS points at the service account.

    The google-auth library honours this env var; setting it here means the
    SDK picks up the right credentials regardless of how the app was launched.
    """
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Service account JSON not found at {creds_path}. "
            "Drop the file there or set GOOGLE_APPLICATION_CREDENTIALS."
        )
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(creds_path)


class GeminiClient:
    """Single Gemini client wrapper used by every capability."""

    def __init__(self, config: Config):
        self.config = config
        _ensure_credentials_visible(config.vertex.credentials_path)

        logger.info(
            "Initialising Vertex AI client (project=%s, location=%s)",
            config.vertex.project_id,
            config.vertex.location,
        )
        self._client = genai.Client(
            vertexai=True,
            project=config.vertex.project_id,
            location=config.vertex.location,
        )

    # ------------------------------------------------------------------
    # Generic call helpers
    # ------------------------------------------------------------------

    def _generate(
        self,
        model: str,
        contents: Iterable[Any] | Any,
        *,
        config: genai_types.GenerateContentConfig | None = None,
    ) -> Any:
        """Single retried call into ``client.models.generate_content``."""

        retry_cfg = self.config.retry

        @retry(
            reraise=True,
            stop=stop_after_attempt(retry_cfg.attempts),
            wait=wait_exponential(
                multiplier=retry_cfg.initial_wait_seconds,
                max=retry_cfg.max_wait_seconds,
            ),
            retry=retry_if_exception_type(Exception),
        )
        def _call() -> Any:
            return self._client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )

        try:
            return _call()
        except Exception as exc:
            logger.exception("Gemini call failed after retries (model=%s)", model)
            raise GeminiCallError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Capability-shaped methods
    # ------------------------------------------------------------------

    def edit_image(
        self,
        *,
        model: str,
        image_bytes: bytes,
        image_mime_type: str,
        instruction: str,
    ) -> GenerationResult:
        """Run a single image-edit call (e.g. Nano Banana Pro)."""
        contents = [
            genai_types.Part.from_bytes(data=image_bytes, mime_type=image_mime_type),
            instruction,
        ]
        response = self._generate(
            model=model,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )
        return _extract(response)

    def transcribe_audio(
        self,
        *,
        model: str,
        audio_bytes: bytes,
        audio_mime_type: str,
        instruction: str | None = None,
    ) -> GenerationResult:
        prompt = instruction or "Transcribe this audio verbatim."
        contents = [
            genai_types.Part.from_bytes(data=audio_bytes, mime_type=audio_mime_type),
            prompt,
        ]
        response = self._generate(model=model, contents=contents)
        return _extract(response)

    def synthesize_speech(
        self,
        *,
        model: str,
        script: str,
        voice_preset: str,
        instruction: str | None = None,
    ) -> GenerationResult:
        """Single TTS call. Caller is responsible for chunking long scripts."""
        prompt = script if not instruction else f"{instruction.strip()}\n\n{script}"
        config = genai_types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=genai_types.SpeechConfig(
                voice_config=genai_types.VoiceConfig(
                    prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(
                        voice_name=voice_preset,
                    )
                )
            ),
        )
        response = self._generate(model=model, contents=prompt, config=config)
        return _extract(response)

    def understand_video(
        self,
        *,
        model: str,
        video_bytes: bytes,
        video_mime_type: str,
        instruction: str,
        response_mime_type: str | None = None,
    ) -> GenerationResult:
        contents = [
            genai_types.Part.from_bytes(data=video_bytes, mime_type=video_mime_type),
            instruction,
        ]
        cfg = None
        if response_mime_type:
            cfg = genai_types.GenerateContentConfig(response_mime_type=response_mime_type)
        response = self._generate(model=model, contents=contents, config=cfg)
        return _extract(response)


def _extract(response: Any) -> GenerationResult:
    """Pull text/image/audio bytes out of a generate_content response."""
    result = GenerationResult(raw=response)
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        parts = getattr(getattr(candidate, "content", None), "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                mime = getattr(inline, "mime_type", "") or ""
                if mime.startswith("image/"):
                    result.image_bytes = inline.data
                    result.image_mime_type = mime
                elif mime.startswith("audio/"):
                    result.audio_bytes = inline.data
                    result.audio_mime_type = mime
            text = getattr(part, "text", None)
            if text:
                result.text = (result.text or "") + text
    return result


@lru_cache(maxsize=1)
def get_client(config: Config | None = None) -> GeminiClient:
    return GeminiClient(config or load_config())
