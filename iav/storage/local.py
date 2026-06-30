"""Local filesystem storage for POC inputs and outputs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2] / "storage"


def inputs_dir() -> Path:
    path = _ROOT / "inputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def outputs_dir() -> Path:
    path = _ROOT / "outputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stamped_name(suffix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}{suffix}"


def save_input(data: bytes, suffix: str) -> Path:
    target = inputs_dir() / _stamped_name(suffix)
    target.write_bytes(data)
    return target


def save_output(data: bytes, suffix: str, capability: str) -> Path:
    target = outputs_dir() / f"{capability}-{_stamped_name(suffix)}"
    target.write_bytes(data)
    return target
