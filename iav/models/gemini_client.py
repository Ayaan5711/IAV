"""Vertex AI client wrapper.

Thin wrapper around the ``google-genai`` SDK configured for Vertex AI. The
rest of the codebase only ever talks to this wrapper — never to the SDK
directly — so authentication, retries, and model-ID indirection are all in
one place.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from google import genai
from google.genai import types as genai_types
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from iav.models.config import Config, load_config
from iav.models.pricing import UsageInfo

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
    video_bytes: bytes | None = None
    video_mime_type: str | None = None
    usage: UsageInfo | None = None
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
        self._clients_by_location: dict[str, genai.Client] = {config.vertex.location: self._client}

    def _client_for(self, location: str | None) -> genai.Client:
        """Returns the default client, or a location-scoped one if given.

        Veo has historically had narrower regional availability than the
        text/image/audio models -- 'global' (the default everywhere else)
        may 404 for video generation even on a project with Veo access.
        Rather than force every capability onto one region, this lets a
        single call target a different location on demand.
        """
        if not location or location == self.config.vertex.location:
            return self._client
        if location not in self._clients_by_location:
            logger.info("Creating a location-scoped client for '%s'", location)
            self._clients_by_location[location] = genai.Client(
                vertexai=True,
                project=self.config.vertex.project_id,
                location=location,
            )
        return self._clients_by_location[location]

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
            before_sleep=before_sleep_log(logger, logging.WARNING),
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
        resolution: str | None = None,
        output_mime_type: str | None = None,
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
                image_config=_image_config(resolution, output_mime_type),
            ),
        )
        return _extract(response)

    def generate_image(
        self,
        *,
        model: str,
        prompt: str,
        resolution: str | None = None,
        output_mime_type: str | None = None,
    ) -> GenerationResult:
        """Pure text-to-image generation -- no input image, unlike edit_image()."""
        response = self._generate(
            model=model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
                image_config=_image_config(resolution, output_mime_type),
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

    def generate_text(
        self,
        *,
        model: str,
        prompt: str,
        response_mime_type: str | None = None,
    ) -> GenerationResult:
        """Plain text-in / text-out call. Used e.g. for transcript cleanup."""
        cfg = None
        if response_mime_type:
            cfg = genai_types.GenerateContentConfig(response_mime_type=response_mime_type)
        response = self._generate(model=model, contents=prompt, config=cfg)
        return _extract(response)

    def synthesize_speech(
        self,
        *,
        model: str,
        script: str,
        voice_preset: str | None = None,
        speakers: list[dict[str, str]] | None = None,
        instruction: str | None = None,
    ) -> GenerationResult:
        """Single TTS call. Caller is responsible for chunking long scripts.

        Pass ``speakers`` (a list of {"speaker": name, "voice": voice_name})
        for multi-speaker narration instead of ``voice_preset`` -- the script
        text must use the same speaker names Gemini sees here.
        """
        prompt = script if not instruction else f"{instruction.strip()}\n\n{script}"

        if speakers:
            speech_config = genai_types.SpeechConfig(
                multi_speaker_voice_config=genai_types.MultiSpeakerVoiceConfig(
                    speaker_voice_configs=[
                        genai_types.SpeakerVoiceConfig(
                            speaker=s["speaker"],
                            voice_config=genai_types.VoiceConfig(
                                prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(
                                    voice_name=s["voice"],
                                )
                            ),
                        )
                        for s in speakers
                    ],
                ),
            )
        else:
            speech_config = genai_types.SpeechConfig(
                voice_config=genai_types.VoiceConfig(
                    prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(
                        voice_name=voice_preset or "Kore",
                    )
                )
            )

        config = genai_types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=speech_config,
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

    def generate_video(
        self,
        *,
        model: str,
        prompt: str,
        duration_seconds: int = 8,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        generate_audio: bool = True,
        poll_interval_seconds: float = 10.0,
        poll_timeout_seconds: float = 360.0,
        location: str | None = None,
    ) -> GenerationResult:
        """Text-to-video via Veo. Long-running: submits a job, polls until done.

        Veo operations don't return usage_metadata the way generate_content
        does -- billing is per second of generated video, not per token, so
        the returned result carries no usage info. Cost is computed
        separately from duration_seconds.
        """
        client = self._client_for(location)
        config = genai_types.GenerateVideosConfig(
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            generate_audio=generate_audio,
        )
        logger.info(
            "generate_video: submitting model=%s duration=%ds resolution=%s location=%s",
            model, duration_seconds, resolution, location or self.config.vertex.location,
        )
        try:
            operation = client.models.generate_videos(model=model, prompt=prompt, config=config)
        except Exception as exc:
            logger.exception("generate_video: submission failed (model=%s)", model)
            raise GeminiCallError(str(exc)) from exc

        elapsed = 0.0
        while not operation.done:
            if elapsed >= poll_timeout_seconds:
                logger.error(
                    "generate_video: timed out after %.0fs waiting on operation %s",
                    elapsed, operation.name,
                )
                raise GeminiCallError(
                    f"Video generation did not finish within {poll_timeout_seconds:.0f}s "
                    "(it may still complete server-side; Veo latency can run up to several minutes)."
                )
            time.sleep(poll_interval_seconds)
            elapsed += poll_interval_seconds
            logger.debug("generate_video: polling operation %s (%.0fs elapsed)", operation.name, elapsed)
            try:
                operation = client.operations.get(operation)
            except Exception as exc:
                logger.exception("generate_video: polling failed after %.0fs", elapsed)
                raise GeminiCallError(str(exc)) from exc

        if operation.error:
            logger.error("generate_video: operation returned an error: %s", operation.error)
            raise GeminiCallError(f"Video generation failed: {operation.error}")

        result = operation.result or operation.response
        generated = (result.generated_videos or [None])[0] if result else None
        if generated is None or generated.video is None:
            logger.error("generate_video: operation completed with no video in the response")
            raise GeminiCallError("Video generation completed but returned no video.")

        video = generated.video
        video_bytes = video.video_bytes
        if not video_bytes and video.uri:
            logger.debug("generate_video: downloading video bytes from %s", video.uri)
            video_bytes = client.files.download(file=generated)

        logger.info(
            "generate_video: completed in %.0fs, %d bytes", elapsed, len(video_bytes or b"")
        )
        logger.info(
            "Gemini response metadata: operation_name=%s operation_metadata=%s mime_type=%s",
            operation.name, operation.metadata, video.mime_type,
        )

        gen_result = GenerationResult(raw=operation)
        gen_result.video_bytes = video_bytes
        gen_result.video_mime_type = video.mime_type or "video/mp4"
        return gen_result


def _image_config(resolution: str | None, output_mime_type: str | None) -> genai_types.ImageConfig | None:
    if not resolution and not output_mime_type:
        return None
    mime = None
    if output_mime_type:
        mime = output_mime_type if "/" in output_mime_type else f"image/{output_mime_type}"
    return genai_types.ImageConfig(image_size=resolution, output_mime_type=mime)


def _extract(response: Any) -> GenerationResult:
    """Pull text/image/audio bytes and token usage out of a response."""
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
    result.usage = _extract_usage(response)
    return result


def _extract_usage(response: Any) -> UsageInfo | None:
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return None

    logger.info(
        "Gemini response metadata: model_version=%s response_id=%s usage_metadata=%s",
        getattr(response, "model_version", None),
        getattr(response, "response_id", None),
        meta.model_dump(exclude_none=True) if hasattr(meta, "model_dump") else meta,
    )

    def _modality_breakdown(details: Any) -> dict[str, int]:
        breakdown: dict[str, int] = {}
        for item in details or []:
            modality = getattr(item, "modality", None)
            count = getattr(item, "token_count", None)
            if modality is None or count is None:
                continue
            key = getattr(modality, "value", str(modality))
            breakdown[key] = breakdown.get(key, 0) + int(count)
        return breakdown

    return UsageInfo(
        prompt_tokens=int(getattr(meta, "prompt_token_count", 0) or 0),
        output_tokens=int(getattr(meta, "candidates_token_count", 0) or 0),
        total_tokens=int(getattr(meta, "total_token_count", 0) or 0),
        prompt_modality_breakdown=_modality_breakdown(getattr(meta, "prompt_tokens_details", None)),
        output_modality_breakdown=_modality_breakdown(getattr(meta, "candidates_tokens_details", None)),
    )


_client_singleton: GeminiClient | None = None


def get_client(config: Config | None = None) -> GeminiClient:
    """Module-level singleton. The first call wins; subsequent calls reuse it."""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = GeminiClient(config or load_config())
    return _client_singleton
