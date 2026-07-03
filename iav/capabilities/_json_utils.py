"""Shared helpers for capabilities that expect structured JSON back from
Gemini (video_to_questions, video_enhance's caption transcription,
audio_question_generation).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class JsonParseError(RuntimeError):
    """Raised when model output cannot be coerced into JSON."""


def parse_json_loose(raw: str) -> Any:
    """Parse JSON, tolerating a model that wrapped the output in a code fence."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", raw, re.DOTALL)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            logger.debug("Recovered JSON from a code fence (model didn't return raw JSON)")
            return parsed
        except json.JSONDecodeError:
            pass

    brace = re.search(r"\{.*\}", raw, re.DOTALL)
    if brace:
        try:
            parsed = json.loads(brace.group(0))
            logger.debug("Recovered JSON by extracting the outermost {...} block")
            return parsed
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse model output as JSON. First 400 chars: %s", raw[:400])
    raise JsonParseError(
        f"Could not parse the model output as JSON. First 400 chars: {raw[:400]}"
    )


def questions_as_markdown(questions: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for i, q in enumerate(questions, start=1):
        stem = q.get("stem") or q.get("question") or "(no stem)"
        lines.append(f"**Q{i}.** {stem}")
        opts = q.get("options")
        if isinstance(opts, list) and opts:
            for j, opt in enumerate(opts):
                letter = chr(ord("A") + j)
                lines.append(f"  - {letter}. {opt}")
        ans = q.get("answer")
        if ans is not None:
            lines.append(f"**Answer:** {ans}")
        expl = q.get("explanation")
        if expl:
            lines.append(f"_Explanation:_ {expl}")
        ts = q.get("timestamp")
        if ts:
            lines.append(f"_Timestamp:_ `{ts}`")
        lines.append("")
    return "\n".join(lines)
