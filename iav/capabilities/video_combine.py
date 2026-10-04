"""Clips → Combined Video.

Conventional ffmpeg pipeline joins several previously-generated clips (any
mix of Veo / Gemini Omni output, or other footage) into one longer file --
the practical way to build a long-form lesson out of several short
generations, since no single video-generation call here natively produces
more than a few seconds (base generation) to ~2.5 minutes (Veo Extend's
documented ceiling) of continuous footage.

Two paths, picked automatically:
    - Fast path: all clips share codec/resolution/frame rate -> concat
      demuxer with stream copy (-c copy). Lossless, near-instant.
    - Fallback: clips differ -> concat filter with a full re-encode, so
      mismatched clips still combine correctly (slower, but routine).

Requires ffmpeg on PATH.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput
from iav.models.config import Config, load_config
from iav.models.pricing import summarize_costs
from iav.storage import output_path

logger = logging.getLogger(__name__)


class VideoCombineError(RuntimeError):
    """Raised when clips cannot be combined into one output."""


class VideoCombine(Capability):
    name = "video_combine"

    def __init__(self, config: Config | None = None):
        self.config = config or load_config()
        self._settings = self.config.capability(self.name)
        if not shutil.which("ffmpeg"):
            raise VideoCombineError(
                "ffmpeg is not on PATH. Install it (e.g. `apt install ffmpeg` "
                "or `brew install ffmpeg`) before using this capability."
            )

    def process(self, payload: CapabilityInput) -> CapabilityOutput:
        params = payload.params or {}
        clip_paths = [Path(p) for p in (params.get("clip_paths") or [])]
        if payload.file_path is not None:
            clip_paths = [Path(payload.file_path), *clip_paths]
        if len(clip_paths) < 2:
            raise ValueError(
                "VideoCombine requires at least two clips (payload.file_path "
                "plus params['clip_paths'], or two-or-more entries in "
                "params['clip_paths'])"
            )
        for clip in clip_paths:
            if not clip.exists():
                raise FileNotFoundError(f"Input clip not found: {clip}")

        encoder = {**self._settings.get("encoder", {}), **params.get("encoder", {})}
        out = output_path(".mp4", self.name)

        mode = self._try_stream_copy(clip_paths, out)
        if mode != "stream_copy":
            mode = self._reencode_concat(clip_paths, out, encoder)

        if not out.exists() or out.stat().st_size == 0:
            raise VideoCombineError("ffmpeg produced no output file.")

        # Pure ffmpeg -- no Gemini call, so cost is always $0, but we still
        # route it through the shared cost summary so metadata['cost'] has
        # the same shape every other capability's output does.
        cost = summarize_costs([], self.config.pricing)

        logger.info(
            "video_combine: combined %d clips via %s -> %s (%d bytes)",
            len(clip_paths),
            mode,
            out,
            out.stat().st_size,
        )

        return CapabilityOutput(
            file_path=out,
            metadata={
                "input_files": [str(clip) for clip in clip_paths],
                "input_count": len(clip_paths),
                "input_bytes": [clip.stat().st_size for clip in clip_paths],
                "output_bytes": out.stat().st_size,
                "mode": mode,
                "mime_type": "video/mp4",
                "cost": cost,
            },
        )

    # ------------------------------------------------------------------
    # ffmpeg
    # ------------------------------------------------------------------

    def _try_stream_copy(self, clips: list[Path], out: Path) -> str:
        """Fast path: concat demuxer + stream copy. Only safe when every
        clip shares codec/resolution/frame rate AND a compatible timebase --
        ffmpeg can exit 0 and still hand back a corrupt result (wrong
        duration, garbled playback) when source clips come from different
        encoder sessions with different internal timebases, even if their
        codec/resolution/fps otherwise match. Confirmed live: concatenating
        a Veo-generated clip with a Gemini-Omni-generated clip (11.00s +
        10.03s of real input) silently produced a file reporting 2:33 of
        duration and 3.29fps instead of ~21s -- exit code 0 throughout. So
        exit code alone is not proof of a correct result; the output
        duration is checked against the sum of the inputs' durations before
        this path is trusted.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as list_file:
            for clip in clips:
                escaped = str(clip.resolve()).replace("'", "'\\''")
                list_file.write(f"file '{escaped}'\n")
            list_path = Path(list_file.name)

        try:
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(list_path), "-c", "copy", str(out),
            ]
            logger.info("video_combine: trying stream-copy concat: %s", " ".join(cmd))
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
                logger.info(
                    "video_combine: stream-copy concat failed (exit %d), falling back to re-encode",
                    proc.returncode,
                )
                return "failed"

            expected = sum(d for d in (_probe_duration_seconds(c) for c in clips) if d is not None)
            actual = _probe_duration_seconds(out)
            if expected > 0 and (actual is None or abs(actual - expected) > max(1.5, expected * 0.1)):
                logger.warning(
                    "video_combine: stream-copy concat exited 0 but duration is wrong "
                    "(expected ~%.1fs, got %s) -- discarding and falling back to re-encode",
                    expected,
                    actual,
                )
                return "failed"
            return "stream_copy"
        finally:
            list_path.unlink(missing_ok=True)

    def _reencode_concat(self, clips: list[Path], out: Path, encoder: dict) -> str:
        """Fallback: concat filter + full re-encode -- works even when
        clips differ in codec/resolution/frame rate."""
        cmd = ["ffmpeg", "-y"]
        for clip in clips:
            cmd += ["-i", str(clip)]

        n = len(clips)
        filter_parts = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
        filter_complex = f"{filter_parts}concat=n={n}:v=1:a=1[outv][outa]"

        cmd += [
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", encoder.get("video_codec", "libx264"),
            "-preset", encoder.get("preset", "medium"),
            "-crf", str(encoder.get("crf", 22)),
            "-c:a", encoder.get("audio_codec", "aac"),
            "-b:a", encoder.get("audio_bitrate", "160k"),
            "-movflags", "+faststart",
            str(out),
        ]
        logger.info("video_combine: re-encode concat: %s", " ".join(cmd))
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if proc.returncode != 0:
            stderr_tail = (proc.stderr or b"").decode("utf-8", errors="replace")[-1500:]
            raise VideoCombineError(
                f"ffmpeg re-encode concat failed with exit code {proc.returncode}. "
                f"Last stderr:\n{stderr_tail}"
            )
        return "reencode"


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def _probe_duration_seconds(path: Path) -> float | None:
    """Read a media file's duration straight from ffmpeg's own stderr
    banner (no ffprobe dependency assumed). Returns None if it can't be
    found -- callers treat that as "can't verify, don't trust this path".
    """
    proc = subprocess.run(
        ["ffmpeg", "-i", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    text = (proc.stderr or b"").decode("utf-8", errors="replace")
    match = _DURATION_RE.search(text)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
