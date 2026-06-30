"""Common interface every capability implements.

Every media-transformation capability (image, audio, video) lives in this
package and exposes the same shape: a single ``process`` call that takes a
``CapabilityInput`` and returns a ``CapabilityOutput``. The Streamlit UI and
any future API only ever talk to this interface, never to a specific Gemini
model ID — that indirection is what lets us swap models as Google deprecates
them without touching business logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CapabilityInput:
    file_path: Path | None = None
    text: str | None = None
    instruction: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class CapabilityOutput:
    file_path: Path | None = None
    text: str | None = None
    data: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Capability(ABC):
    name: str

    @abstractmethod
    def process(self, payload: CapabilityInput) -> CapabilityOutput:
        ...
