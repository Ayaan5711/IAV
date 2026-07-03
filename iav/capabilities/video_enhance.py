"""Video → Professional.

Conventional ffmpeg pipeline does the actual enhancement work; Gemini's
role is transcription (for auto-captions) and optional issue flagging.

The SME's original voice is preserved — we denoise it, we don't regenerate
it as TTS. Students watching the lecture should hear the actual teacher.

Pipeline (default):
    input video
      └─ Gemini transcribes audio → SRT
      └─ ffmpeg single command:
           video: deshake (stabilise) + eq (light colour correction)
                  + subtitles (burn captions)
           audio: afftdn (light denoise)
      └─ output MP4

Requires ffmpeg on PATH.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from iav.capabilities._json_utils import JsonParseError, parse_json_loose
from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput
from iav.models.config import Config, load_config
from iav.models.gemini_client import GeminiCallError, GeminiClient, get_client
from iav.models.pricing import summarize_costs
from iav.storage import output_path

logger = logging.getLogger(__name__)


class VideoEnhanceError(RuntimeError):
    """Raised when video enhancement cannot produce an output."""


class VideoEnhance(Capability):
    name = "video_enhance"

    def __init__(self, client: GeminiClient | None = None, config: Config | None = None):
        self.config = config or load_config()
        self.client = client or get_client(self.config)
        self._settings = self.config.capability(self.name)
        if not shutil.which("ffmpeg"):
            raise VideoEnhanceError(
                "ffmpeg is not on PATH. Install it (e.g. `apt install ffmpeg` "
                "or `brew install ffmpeg`) before using this capability."
            )

    def process(self, payload: CapabilityInput) -> CapabilityOutput:
        if payload.file_path is None:
            raise ValueError("VideoEnhance requires an input video file path")
        source = Path(payload.file_path)
        if not source.exists():
            raise FileNotFoundError(f"Input video not found: {source}")

        params = payload.params or {}
        pipeline = {**self._settings.get("pipeline", {}), **params.get("pipeline", {})}
        encoder = {**self._settings.get("encoder", {}), **params.get("encoder", {})}
        caption_cfg = self._settings.get("captions", {})
        model = params.get("model") or os.environ.get("GEMINI_VIDEO_MODEL") or self._settings["analysis_model"]

        with tempfile.TemporaryDirectory(prefix="iav-video-") as tmp:
            work = Path(tmp)
            srt_path: Path | None = None
            segments: list[dict[str, Any]] = []
            calls: list[dict[str, Any]] = []

            if pipeline.get("auto_captions", True):
                segments, transcribe_usage = self._transcribe(model, source)
                calls.append({"label": "transcribe_captions", "model": model, "usage": transcribe_usage})
                if segments:
                    srt_path = work / "captions.srt"
                    srt_path.write_text(_segments_to_srt(segments), encoding="utf-8")
                    logger.info(
                        "video_enhance: wrote %d caption segments to %s",
                        len(segments),
                        srt_path,
                    )
                else:
                    logger.warning(
                        "video_enhance: transcription returned no segments; skipping captions"
                    )

            issues: str | None = None
            if pipeline.get("flag_issues", False):
                issues, issues_usage = self._flag_issues(model, source)
                calls.append({"label": "flag_issues", "model": model, "usage": issues_usage})

            cost = summarize_costs(calls, self.config.pricing)

            out = output_path(".mp4", self.name)
            self._run_ffmpeg(
                source=source,
                output=out,
                srt_path=srt_path,
                pipeline=pipeline,
                encoder=encoder,
                caption_cfg=caption_cfg,
            )

            if not out.exists() or out.stat().st_size == 0:
                raise VideoEnhanceError("ffmpeg produced no output file.")

            logger.info(
                "video_enhance: wrote %s (%d bytes, est. cost $%.6f)",
                out,
                out.stat().st_size,
                cost["total_usd"],
            )

            return CapabilityOutput(
                file_path=out,
                text=_segments_to_srt(segments) if segments else None,
                data={"segments": segments, "issues": issues} if segments or issues else None,
                metadata={
                    "model": model,
                    "input_file": str(source),
                    "input_bytes": source.stat().st_size,
                    "output_bytes": out.stat().st_size,
                    "captioned": bool(segments),
                    "caption_count": len(segments),
                    "issues": issues,
                    "mime_type": "video/mp4",
                    "pipeline_applied": {
                        k: bool(v)
                        for k, v in pipeline.items()
                    },
                    "cost": cost,
                },
            )

    # ------------------------------------------------------------------
    # Gemini calls
    # ------------------------------------------------------------------

    def _transcribe(self, model: str, source: Path) -> tuple[list[dict[str, Any]], Any]:
        video_bytes = source.read_bytes()
        mime_type = _guess_video_mime(source)
        instruction = self._settings.get("transcript_instruction", "")
        try:
            result = self.client.understand_video(
                model=model,
                video_bytes=video_bytes,
                video_mime_type=mime_type,
                instruction=instruction,
                response_mime_type="application/json",
            )
        except GeminiCallError as exc:
            raise VideoEnhanceError(f"Caption transcription failed: {exc}") from exc

        raw_text = (result.text or "").strip()
        if not raw_text:
            return [], result.usage
        try:
            parsed = parse_json_loose(raw_text)
        except JsonParseError as exc:
            raise VideoEnhanceError(str(exc)) from exc
        segments = parsed.get("segments") if isinstance(parsed, dict) else None
        if not isinstance(segments, list):
            return [], result.usage
        return [s for s in segments if isinstance(s, dict)], result.usage

    def _flag_issues(self, model: str, source: Path) -> tuple[str | None, Any]:
        video_bytes = source.read_bytes()
        mime_type = _guess_video_mime(source)
        prompt = (
            "Review this teaching recording and list any production issues a "
            "video editor should address: poor audio sections (with timestamps), "
            "shaky shots, framing problems, lighting issues, sections that "
            "should be cut, or anything else that detracts from instructional "
            "quality. Be concise — bullet points only."
        )
        try:
            result = self.client.understand_video(
                model=model,
                video_bytes=video_bytes,
                video_mime_type=mime_type,
                instruction=prompt,
            )
        except GeminiCallError as exc:
            logger.warning("Issue flagging failed: %s", exc)
            return None, None
        return (result.text or "").strip() or None, result.usage

    # ------------------------------------------------------------------
    # ffmpeg
    # ------------------------------------------------------------------

    def _run_ffmpeg(
        self,
        *,
        source: Path,
        output: Path,
        srt_path: Path | None,
        pipeline: dict[str, Any],
        encoder: dict[str, Any],
        caption_cfg: dict[str, Any],
    ) -> None:
        video_filters: list[str] = []
        audio_filters: list[str] = []

        if pipeline.get("stabilize", True):
            video_filters.append("deshake")
        if pipeline.get("light_color_correction", True):
            video_filters.append("eq=saturation=1.05:contrast=1.04:gamma=0.97")
        if srt_path is not None:
            font_size = int(caption_cfg.get("font_size", 20))
            # Path escaping for the subtitles filter: backslashes and colons need
            # quoting on some platforms. Using forward slashes works on Linux.
            srt_arg = str(srt_path).replace("\\", "/")
            video_filters.append(
                f"subtitles='{srt_arg}':force_style='FontSize={font_size},"
                f"PrimaryColour=&HFFFFFF&,BackColour=&H80000000&,BorderStyle=4'"
            )

        if pipeline.get("audio_denoise", True):
            audio_filters.append("afftdn=nr=12")

        cmd: list[str] = ["ffmpeg", "-y", "-i", str(source)]
        if video_filters:
            cmd += ["-vf", ",".join(video_filters)]
        if audio_filters:
            cmd += ["-af", ",".join(audio_filters)]
        cmd += [
            "-c:v", encoder.get("video_codec", "libx264"),
            "-preset", encoder.get("preset", "medium"),
            "-crf", str(encoder.get("crf", 22)),
            "-c:a", encoder.get("audio_codec", "aac"),
            "-b:a", encoder.get("audio_bitrate", "160k"),
            "-movflags", "+faststart",
            str(output),
        ]

        logger.info("video_enhance: running ffmpeg: %s", " ".join(cmd))
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode != 0:
            stderr_tail = (proc.stderr or b"").decode("utf-8", errors="replace")[-1500:]
            raise VideoEnhanceError(
                f"ffmpeg failed with exit code {proc.returncode}. "
                f"Last stderr:\n{stderr_tail}"
            )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _guess_video_mime(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed and guessed.startswith("video/"):
        return guessed
    suffix = path.suffix.lower().lstrip(".")
    fallback = {
        "mp4": "video/mp4",
        "mov": "video/quicktime",
        "webm": "video/webm",
        "mkv": "video/x-matroska",
        "avi": "video/x-msvideo",
    }
    if suffix in fallback:
        return fallback[suffix]
    raise ValueError(f"Unsupported video format: {path.suffix}")


_TS_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?$")


def _ts_to_srt(ts: str) -> str:
    """Convert MM:SS.mmm or HH:MM:SS.mmm to SRT's HH:MM:SS,mmm format."""
    m = _TS_RE.match(ts.strip())
    if not m:
        return "00:00:00,000"
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2))
    seconds = int(m.group(3))
    millis = int((m.group(4) or "0").ljust(3, "0")[:3])
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _segments_to_srt(segments: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        start = _ts_to_srt(str(seg.get("start", "00:00.000")))
        end = _ts_to_srt(str(seg.get("end", "00:00.000")))
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)
