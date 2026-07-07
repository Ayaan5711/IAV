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
    pricing: dict[str, Any] = field(default_factory=dict)
    languages: dict[str, Any] = field(default_factory=dict)
    azure_openai: dict[str, Any] = field(default_factory=dict)
    log_level: str = "INFO"

    def capability(self, name: str) -> dict[str, Any]:
        if name not in self.capabilities:
            raise KeyError(f"No config entry for capability '{name}'")
        return self.capabilities[name]


def _resolve_credentials_path() -> Path:
    """Resolve the service account JSON path.

    Honoured env vars (in priority order):
      1. GOOGLE_APPLICATION_CREDENTIALS  (Google's standard)
      2. GEMINI_CREDENTIALS              (path OR raw JSON content)

    Falls back to .credentials/service-account.json in the repo root.
    """
    env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path:
        return Path(env_path).expanduser()

    gemini_creds = os.environ.get("GEMINI_CREDENTIALS")
    if gemini_creds:
        stripped = gemini_creds.strip()
        if stripped.startswith("{"):
            # Inline JSON content — write to .credentials/ so the SDK can read it.
            inline_path = _DEFAULT_CREDS.parent / "service-account.json"
            inline_path.parent.mkdir(parents=True, exist_ok=True)
            inline_path.write_text(stripped, encoding="utf-8")
            return inline_path
        return Path(stripped).expanduser()

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
    """Resolve project_id and location from env vars, config, or creds file.

    Env vars honoured (each in priority order):
      project_id: VERTEX_AI_PROJECT_ID -> PROJECT_ID -> config.yaml -> creds JSON
      location:   VERTEX_AI_LOCATION   -> GEMINI_LOCATION -> config.yaml -> "us-central1"
    """
    creds_path = _resolve_credentials_path()
    project_id = (
        os.environ.get("VERTEX_AI_PROJECT_ID")
        or os.environ.get("PROJECT_ID")
        or raw.get("project_id")
    )
    location = (
        os.environ.get("VERTEX_AI_LOCATION")
        or os.environ.get("GEMINI_LOCATION")
        or raw.get("location")
        or "global"
    )

    if not project_id:
        try:
            project_id = _read_credentials(creds_path).get("project_id")
            logger.info("project_id not set via env/config; read from %s", creds_path)
        except FileNotFoundError:
            project_id = None

    if not project_id:
        logger.error("Could not resolve project_id from env, config.yaml, or %s", creds_path)
        raise RuntimeError(
            "Could not resolve project_id. Set VERTEX_AI_PROJECT_ID or "
            "PROJECT_ID, fill vertex_ai.project_id in config.yaml, or "
            f"place the service account JSON at {_DEFAULT_CREDS} so "
            "project_id can be read from it."
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
        logger.error("Config file not found at %s", config_path)
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

    logger.info(
        "Config loaded from %s (project=%s, location=%s, %d capabilities)",
        config_path, vertex.project_id, vertex.location, len(raw.get("capabilities", {}) or {}),
    )

    return Config(
        vertex=vertex,
        retry=retry,
        capabilities=raw.get("capabilities", {}) or {},
        pricing=raw.get("pricing", {}) or {},
        languages=raw.get("languages", {}) or {},
        azure_openai=raw.get("azure_openai", {}) or {},
        log_level=log_level,
    )
