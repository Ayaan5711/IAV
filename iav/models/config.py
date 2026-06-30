"""Config loader.

Reads ``config.yaml`` from the repo root and resolves Vertex AI project /
location from the service account JSON when not pinned in config.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG = _REPO_ROOT / "config.yaml"
_DEFAULT_CREDS = _REPO_ROOT / ".credentials" / "service-account.json"


@dataclass
class VertexConfig:
    project_id: str
    location: str
    credentials_path: Path


@dataclass
class RetryConfig:
    attempts: int = 3
    initial_wait_seconds: float = 1.5
    max_wait_seconds: float = 30.0


@dataclass
class Config:
    vertex: VertexConfig
    retry: RetryConfig
    capabilities: dict[str, dict[str, Any]] = field(default_factory=dict)
    log_level: str = "INFO"

    def capability(self, name: str) -> dict[str, Any]:
        if name not in self.capabilities:
            raise KeyError(f"No config entry for capability '{name}'")
        return self.capabilities[name]


def _resolve_credentials_path() -> Path:
    env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path:
        return Path(env_path).expanduser()
    return _DEFAULT_CREDS


def _read_credentials(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Service account JSON not found at {path}. "
            "Place the file there or set GOOGLE_APPLICATION_CREDENTIALS."
        )
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _resolve_vertex_settings(raw: dict[str, Any]) -> VertexConfig:
    creds_path = _resolve_credentials_path()
    project_id = (
        os.environ.get("VERTEX_AI_PROJECT_ID")
        or raw.get("project_id")
    )
    location = (
        os.environ.get("VERTEX_AI_LOCATION")
        or raw.get("location")
        or "us-central1"
    )

    if not project_id:
        try:
            project_id = _read_credentials(creds_path).get("project_id")
        except FileNotFoundError:
            project_id = None

    if not project_id:
        raise RuntimeError(
            "Could not resolve Vertex AI project_id. Either set "
            "VERTEX_AI_PROJECT_ID, fill vertex_ai.project_id in config.yaml, "
            "or place the service account JSON at "
            f"{_DEFAULT_CREDS} so project_id can be read from it."
        )

    return VertexConfig(
        project_id=project_id,
        location=location,
        credentials_path=creds_path,
    )


@lru_cache(maxsize=1)
def load_config(path: Path | None = None) -> Config:
    config_path = Path(path) if path else _DEFAULT_CONFIG
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found at {config_path}")

    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    vertex = _resolve_vertex_settings(raw.get("vertex_ai", {}))
    retry_raw = raw.get("retry", {})
    retry = RetryConfig(
        attempts=int(retry_raw.get("attempts", 3)),
        initial_wait_seconds=float(retry_raw.get("initial_wait_seconds", 1.5)),
        max_wait_seconds=float(retry_raw.get("max_wait_seconds", 30.0)),
    )
    log_level = os.environ.get("LOG_LEVEL") or raw.get("logging", {}).get("level", "INFO")

    return Config(
        vertex=vertex,
        retry=retry,
        capabilities=raw.get("capabilities", {}) or {},
        log_level=log_level,
    )
