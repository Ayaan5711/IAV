"""Generate Video — structured prompt → new scenario-based video (Veo).

Real constraints, not hidden: Veo is Preview-only (no Stable model exists
today), clips run 4-8 seconds, generation takes anywhere from ~11 seconds to
several minutes, and it bills per second of output rather than per token.
"Scenario Based" video from a spec doesn't mean a full multi-scene video --
it means one short generated clip.
"""

from __future__ import annotations

import logging
import os

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


class VideoGenerateError(RuntimeError):
    """Raised when video generation cannot produce an output."""


class VideoGenerate(Capability):
    name = "video_generate"

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

        errors = validate_common_attributes(common) + validate_free_text(free_text)
        if errors:
            raise ValueError("; ".join(errors))

        model = os.environ.get("GEMINI_VEO_MODEL") or params.get("model") or self._settings["model"]
        resolution = params.get("resolution") or self._settings.get("resolution", "720p")
        duration_seconds = int(params.get("duration_seconds") or self._settings.get("duration_seconds", 8))
        generate_audio = bool(params.get("generate_audio", self._settings.get("generate_audio", True)))
        video_type = params.get("video_type") or self._settings["video_types"][0]
        poll_interval = float(self._settings.get("poll_interval_seconds", 10))
        poll_timeout = float(self._settings.get("poll_timeout_seconds", 360))

        prompt = self._settings["prompt_template"].format(
            video_type=video_type, common_block=common_block(common), free_text=free_text
        )

        logger.info(
            "video_generate: model=%s resolution=%s duration=%ds",
            model, resolution, duration_seconds,
        )

        try:
            result = self.client.generate_video(
                model=model,
                prompt=prompt,
                duration_seconds=duration_seconds,
                resolution=resolution,
                generate_audio=generate_audio,
                poll_interval_seconds=poll_interval,
                poll_timeout_seconds=poll_timeout,
            )
        except GeminiCallError as exc:
            raise VideoGenerateError(f"Veo call failed: {exc}") from exc

        if not result.video_bytes:
            raise VideoGenerateError("Veo returned no video bytes.")

        output_path = save_output(
            data=result.video_bytes,
            suffix=".mp4",
            capability=self.name,
        )
        cost = summarize_costs(
            [
                {
                    "label": "video_generate",
                    "model": model,
                    "usage": None,
                    "duration_seconds": duration_seconds,
                    "resolution": resolution,
                }
            ],
            self.config.pricing,
        )

        logger.info("video_generate: wrote %s, est. cost $%.6f", output_path, cost["total_usd"])

        return CapabilityOutput(
            file_path=output_path,
            text=prompt,
            metadata={
                "model": model,
                "video_type": video_type,
                "resolution": resolution,
                "duration_seconds": duration_seconds,
                "generate_audio": generate_audio,
                "output_bytes": len(result.video_bytes),
                "mime_type": result.video_mime_type or "video/mp4",
                "cost": cost,
            },
        )
