"""Audio → Audio (ASR + cleanup + TTS). Placeholder until Phase 2."""

from __future__ import annotations

from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput


class AudioToAudio(Capability):
    name = "audio_to_audio"

    def process(self, payload: CapabilityInput) -> CapabilityOutput:
        raise NotImplementedError("Audio-to-Audio lands in Phase 2.")
