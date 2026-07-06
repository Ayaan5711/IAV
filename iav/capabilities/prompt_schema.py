"""Structured prompt schema + validation for the generate-from-scratch capabilities.

Shared by image_generate, audio_generate, video_generate: a common set of
assessment metadata fields, plus per-media attributes, get assembled into
one natural-language prompt and checked for junk input before anything
reaches Gemini. The checks here are a first-pass junk/injection filter,
not a security boundary -- Gemini's own safety filters are the real gate.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MAX_FIELD_LEN = 200
MIN_FREE_TEXT_LEN = 3
MAX_FREE_TEXT_LEN = 2000

_JUNK_REPEAT_RE = re.compile(r"(.)\1{19,}")
_INJECTION_PATTERNS = [
    re.compile(r"ignore (all|any|previous|the above)", re.IGNORECASE),
    re.compile(r"disregard (all|any|previous|the above)", re.IGNORECASE),
    re.compile(r"\byou are now\b", re.IGNORECASE),
    re.compile(r"^\s*system\s*:", re.IGNORECASE),
    re.compile(r"new instructions\s*:", re.IGNORECASE),
]


@dataclass
class CommonAttributes:
    assessment_outcome: str = ""
    difficulty_level: str = "medium"
    target_audience: str = "undergraduate"
    question_type: str = "mcq"


def validate_text_field(
    name: str,
    value: str,
    *,
    min_len: int = 1,
    max_len: int = MAX_FIELD_LEN,
    required: bool = True,
) -> list[str]:
    errors: list[str] = []
    stripped = (value or "").strip()

    if not stripped:
        if required:
            errors.append(f"{name} is required.")
        return errors

    if len(stripped) < min_len:
        errors.append(f"{name} is too short (minimum {min_len} characters).")
    if len(stripped) > max_len:
        errors.append(f"{name} is too long (maximum {max_len} characters).")
    if _JUNK_REPEAT_RE.search(stripped):
        errors.append(f"{name} looks like junk input (excessive character repetition).")
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(stripped):
            errors.append(f"{name} contains a phrase that looks like an attempt to override instructions.")
            logger.warning("Rejected '%s': matched injection pattern %r", name, pattern.pattern)
            break

    if errors:
        logger.info("Validation rejected '%s' (%d issue(s)): %s", name, len(errors), stripped[:80])

    return errors


def validate_common_attributes(common: CommonAttributes) -> list[str]:
    return validate_text_field(
        "Assessment outcome", common.assessment_outcome, min_len=3, max_len=MAX_FIELD_LEN, required=False
    )


def validate_free_text(free_text: str, *, required: bool = True) -> list[str]:
    return validate_text_field(
        "Prompt", free_text, min_len=MIN_FREE_TEXT_LEN, max_len=MAX_FREE_TEXT_LEN, required=required
    )


def common_block(common: CommonAttributes) -> str:
    """Renders the shared attributes as a text block for a prompt template."""
    lines = []
    if common.assessment_outcome.strip():
        lines.append(f"Assessment outcome: {common.assessment_outcome}")
    lines.append(f"Difficulty level: {common.difficulty_level}")
    lines.append(f"Target audience: {common.target_audience}")
    lines.append(f"Question type: {common.question_type}")
    return "\n".join(lines)
