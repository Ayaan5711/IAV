"""Text → Audio (TTS). Placeholder until Phase 2."""

from __future__ import annotations

from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput


class TextToSpeech(Capability):
    name = "audio_text_to_speech"

    def process(self, payload: CapabilityInput) -> CapabilityOutput:  # noqa: D401
        raise NotImplementedError("Text-to-Audio lands in Phase 2.")
