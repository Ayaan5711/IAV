"""Image enhancement — hand-drawn diagram → professional render.

Wraps Nano Banana Pro behind the unified Capability interface. The default
instruction (in ``config.yaml``) is tuned to preserve labels, numbers, and
geometric relationships exactly — non-negotiable for exam-paper diagrams.
"""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path

from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput
from iav.models.config import Config, load_config
from iav.models.gemini_client import GeminiCallError, GeminiClient, get_client
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
        # Allow quick model swaps without editing config — handy while figuring
        # out which image-gen model the Vertex project is allowlisted for.
        model = os.environ.get("GEMINI_IMAGE_MODEL") or self._settings["model"]

        logger.info(
            "image_enhance: invoking model=%s on file=%s (%d bytes)",
            model,
            source.name,
            len(image_bytes),
        )

        try:
            result = self.client.edit_image(
                model=model,
                image_bytes=image_bytes,
                image_mime_type=mime_type,
                instruction=instruction,
            )
        except GeminiCallError as exc:
            raise ImageEnhanceError(f"Gemini call failed: {exc}") from exc

        if not result.image_bytes:
            note = (result.text or "").strip() or "(no detail)"
            raise ImageEnhanceError(
                "Model returned no image. This typically means a safety filter "
                f"blocked the output. Model said: {note}"
            )

        output_path = save_output(
            data=result.image_bytes,
            suffix=_suffix_for_mime(result.image_mime_type),
            capability=self.name,
        )

        logger.info("image_enhance: wrote %s (%d bytes)", output_path, len(result.image_bytes))

        return CapabilityOutput(
            file_path=output_path,
            text=result.text,
            metadata={
                "model": model,
                "input_file": str(source),
                "input_bytes": len(image_bytes),
                "output_bytes": len(result.image_bytes),
                "mime_type": result.image_mime_type,
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
