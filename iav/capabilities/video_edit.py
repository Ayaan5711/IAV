"""Video → Video (edit / extend footage that already exists).

Two genuinely different mechanisms, both real video-to-video -- see
config.yaml -> video_edit for the constraints on each:

    veo_extend   -- continues a clip Veo ITSELF previously generated.
    omni_edit    -- transforms ARBITRARY footage per a text instruction.
    omni_extend  -- continues ARBITRARY footage.

"Arbitrary" above means: not limited to this app's own prior output,
unlike veo_extend. Omni currently only reaches the preview-named model on
this account (see config.yaml's notes) -- a real risk to flag in any UI
built on this, not a reason to hide the capability.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput
from iav.models.config import Config, load_config
from iav.models.gemini_client import GeminiCallError, GeminiClient, get_client
from iav.models.pricing import summarize_costs
from iav.storage import save_output

logger = logging.getLogger(__name__)

_MODES = {"veo_extend", "omni_edit", "omni_extend"}


class VideoEditError(RuntimeError):
    """Raised when a video-to-video call cannot produce an output."""


class VideoEdit(Capability):
    name = "video_edit"

    def __init__(self, client: GeminiClient | None = None, config: Config | None = None):
        self.config = config or load_config()
        self.client = client or get_client(self.config)
        self._settings = self.config.capability(self.name)

    def process(self, payload: CapabilityInput) -> CapabilityOutput:
        if payload.file_path is None:
            raise ValueError("VideoEdit requires an input video file path")
        source = Path(payload.file_path)
        if not source.exists():
            raise FileNotFoundError(f"Input video not found: {source}")

        params = payload.params or {}
        mode = params.get("mode", "veo_extend")
        if mode not in _MODES:
            raise ValueError(f"Unknown mode '{mode}', expected one of {sorted(_MODES)}")

        video_bytes = source.read_bytes()
        mime_type = _guess_video_mime(source)
        instruction = (payload.instruction or "").strip()

        if mode == "veo_extend":
            model = params.get("model") or self._settings["veo_model"]
            location = params.get("location") or self._settings.get("veo_location")
            poll_interval = float(self._settings.get("poll_interval_seconds", 10))
            poll_timeout = float(self._settings.get("poll_timeout_seconds", 360))
            logger.info("video_edit: veo_extend model=%s location=%s input_bytes=%d", model, location, len(video_bytes))
            try:
                result = self.client.extend_video(
                    model=model,
                    video_bytes=video_bytes,
                    video_mime_type=mime_type,
                    prompt=instruction or None,
                    poll_interval_seconds=poll_interval,
                    poll_timeout_seconds=poll_timeout,
                    location=location,
                )
            except GeminiCallError as exc:
                raise VideoEditError(f"Veo Extend call failed: {exc}") from exc
            cost = summarize_costs(
                [{
                    "label": "veo_extend",
                    "model": model,
                    "usage": None,
                    "duration_seconds": float(self._settings.get("veo_extend_added_seconds", 7)),
                    "resolution": "720p",
                }],
                self.config.pricing,
            )
        else:
            if not instruction:
                raise ValueError(f"mode='{mode}' requires an instruction describing the change")
            model = params.get("model") or self._settings["omni_model"]
            task = "edit" if mode == "omni_edit" else "extend"
            logger.info("video_edit: %s model=%s input_bytes=%d", mode, model, len(video_bytes))
            try:
                result = self.client.interactions_video(
                    model=model,
                    instruction=instruction,
                    task=task,
                    video_bytes=video_bytes,
                    video_mime_type=mime_type,
                )
            except GeminiCallError as exc:
                raise VideoEditError(f"Gemini Omni call failed: {exc}") from exc
            # No officially published per-second or per-token rate for this
            # model yet -- summarize_costs() reports $0/unverified with a
            # clear note rather than this capability inventing a number.
            cost = summarize_costs([{"label": mode, "model": model, "usage": result.usage}], self.config.pricing)

        if not result.video_bytes:
            raise VideoEditError(f"{mode}: model returned no video bytes.")

        output_path = save_output(data=result.video_bytes, suffix=".mp4", capability=self.name)

        logger.info("video_edit: wrote %s (%s, est. cost $%.6f)", output_path, mode, cost["total_usd"])

        return CapabilityOutput(
            file_path=output_path,
            metadata={
                "mode": mode,
                "model": model,
                "input_file": str(source),
                "input_bytes": len(video_bytes),
                "output_bytes": len(result.video_bytes),
                "mime_type": result.video_mime_type or "video/mp4",
                "cost": cost,
            },
        )


def _guess_video_mime(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed and guessed.startswith("video/"):
        return guessed
    suffix = path.suffix.lower().lstrip(".")
    fallback = {
        "mp4": "video/mp4",
        "mov": "video/quicktime",
        "webm": "video/webm",
        "mkv": "video/x-matroska",
        "avi": "video/x-msvideo",
    }
    if suffix in fallback:
        return fallback[suffix]
    raise ValueError(f"Unsupported video format: {path.suffix}")
