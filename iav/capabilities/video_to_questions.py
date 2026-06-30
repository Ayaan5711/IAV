"""Video → Questions (Gemini video understanding). Placeholder until Phase 3."""

from __future__ import annotations

from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput


class VideoToQuestions(Capability):
    name = "video_to_questions"

    def process(self, payload: CapabilityInput) -> CapabilityOutput:
        raise NotImplementedError("Video-to-Questions lands in Phase 3.")
