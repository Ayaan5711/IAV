"""Video → Professional video (hybrid pipeline). Placeholder until Phase 4."""

from __future__ import annotations

from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput


class VideoEnhance(Capability):
    name = "video_enhance"

    def process(self, payload: CapabilityInput) -> CapabilityOutput:
        raise NotImplementedError("Video-to-Professional lands in Phase 4.")
