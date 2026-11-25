"""Hybrid long-form segment generator.

Combines three different production techniques into one educational video
segment, using capabilities that already exist in this repo:

    veo beat         -> Veo 3.1 generates a realistic/cinematic clip
                        (optionally frame-chained from the prior beat)
    infographic beat -> Nano Banana (gemini-3.1-flash-image) generates a
                        crisp slide image, ffmpeg animates it into a clip
                        with a slow Ken Burns zoom (no motion inside the
                        graphic itself -- the still+motion treatment is
                        deliberate: Veo is bad at infographics, Nano
                        Banana is great at text and precise geometry but
                        produces stills, so we combine the two)
    narration        -> Gemini TTS generates one voice track across the
                        whole segment, muxed over the final silent video

This is the design that came out of this session's live-tested finding
that Veo alone can't handle abstract infographic segments at publication
quality, while Nano Banana + ffmpeg handles them well. Documented in
docs/VIDEO_CAPABILITIES.md.

Not a general-purpose "generate a whole educational video from a topic"
capability -- that's video_long_form in the same doc. This one takes an
already-planned beat sequence and produces one segment, as the
building block the long-form capability will eventually call.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from iav.capabilities.base import Capability, CapabilityInput, CapabilityOutput
from iav.capabilities.video_combine import VideoCombine
from iav.models.config import Config, load_config
from iav.models.gemini_client import GeminiCallError, GeminiClient, get_client
from iav.models.pricing import summarize_costs
from iav.storage import output_path, save_output

logger = logging.getLogger(__name__)


class VideoHybridSegmentError(RuntimeError):
    """Raised when a hybrid segment cannot be assembled end-to-end."""


@dataclass
class Beat:
    """One beat (clip) inside the segment. Enforced lightly -- the real
    validation happens when the respective generator is called."""

    kind: str  # "veo" | "infographic"
    prompt: str  # Veo scene description OR Nano Banana image prompt
    duration_seconds: int = 8
    chain_from_previous: bool = False  # veo only; use prior beat's last frame
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SegmentPlan:
    """The full plan for one hybrid segment."""

    title: str
    beats: list[Beat]
    narration_script: str  # covers the whole segment start-to-end


class VideoHybridSegment(Capability):
    name = "video_hybrid_segment"

    def __init__(self, client: GeminiClient | None = None, config: Config | None = None):
        self.config = config or load_config()
        self.client = client or get_client(self.config)
        self._settings = self.config.capability(self.name)
        if not shutil.which("ffmpeg"):
            raise VideoHybridSegmentError(
                "ffmpeg is not on PATH. Install it (e.g. `apt install ffmpeg`) before "
                "using this capability."
            )

    def process(self, payload: CapabilityInput) -> CapabilityOutput:
        plan = (payload.params or {}).get("plan")
        if not isinstance(plan, SegmentPlan):
            raise ValueError(
                "VideoHybridSegment requires params['plan'] to be a SegmentPlan "
                "instance (see this module's docstring)."
            )
        if not plan.beats:
            raise ValueError("SegmentPlan must contain at least one beat.")

        veo_model = (payload.params or {}).get("veo_model") or self._settings["veo_model"]
        veo_location = (payload.params or {}).get("veo_location") or self._settings["veo_location"]
        image_model = (payload.params or {}).get("image_model") or self._settings["image_model"]
        tts_model = (payload.params or {}).get("tts_model") or self._settings["tts_model"]
        tts_voice = (payload.params or {}).get("tts_voice") or self._settings["tts_voice"]
        resolution = self._settings.get("resolution", "720p")
        width, height = _resolution_wh(resolution)

        with tempfile.TemporaryDirectory(prefix="iav-hybrid-") as tmp_dir:
            work = Path(tmp_dir)
            clip_paths: list[Path] = []
            last_frame_bytes: bytes | None = None
            calls: list[dict[str, Any]] = []

            # ------------------------------------------------------------
            # 1. Generate each beat's video clip sequentially (sequential
            #    is required anyway when beats chain from the previous
            #    beat's last frame).
            # ------------------------------------------------------------
            for i, beat in enumerate(plan.beats):
                logger.info(
                    "video_hybrid_segment: beat %d/%d kind=%s duration=%ds chain=%s",
                    i + 1, len(plan.beats), beat.kind, beat.duration_seconds, beat.chain_from_previous,
                )
                if beat.kind == "veo":
                    clip = self._generate_veo_beat(
                        beat=beat,
                        model=veo_model,
                        location=veo_location,
                        image_bytes=last_frame_bytes if beat.chain_from_previous else None,
                    )
                    calls.append({
                        "label": f"beat{i+1}_veo",
                        "model": veo_model,
                        "usage": None,
                        "duration_seconds": float(beat.duration_seconds),
                        "resolution": resolution,
                    })
                    last_frame_bytes = _extract_last_frame_jpeg(clip, work / f"beat{i+1}_last.jpg")
                elif beat.kind == "infographic":
                    clip, image_usage = self._generate_infographic_beat(
                        beat=beat,
                        model=image_model,
                        width=width,
                        height=height,
                        work=work,
                        index=i + 1,
                    )
                    calls.append({
                        "label": f"beat{i+1}_infographic",
                        "model": image_model,
                        "usage": image_usage,
                    })
                    # Last-frame continuity doesn't carry across an
                    # infographic beat -- the next veo beat should start
                    # fresh unless caller explicitly chains from an
                    # earlier veo clip (future enhancement).
                    last_frame_bytes = None
                else:
                    raise ValueError(f"Unknown beat kind: {beat.kind!r}")
                clip_paths.append(clip)

            # ------------------------------------------------------------
            # 2. Generate the narration track (one call across the full
            #    script -- Gemini TTS handles paragraphs fine; chunking
            #    isn't needed at segment scale).
            # ------------------------------------------------------------
            logger.info(
                "video_hybrid_segment: generating narration (%d chars) via %s voice=%s",
                len(plan.narration_script), tts_model, tts_voice,
            )
            narration_wav, tts_usage = self._generate_narration(
                script=plan.narration_script,
                model=tts_model,
                voice=tts_voice,
                work=work,
            )
            calls.append({"label": "narration_tts", "model": tts_model, "usage": tts_usage})

            # ------------------------------------------------------------
            # 3. Combine all beat clips into one silent video.
            # ------------------------------------------------------------
            combined_silent = self._combine_beats(clip_paths, work / "combined_silent.mp4")

            # ------------------------------------------------------------
            # 4. Mux narration over the combined silent video.
            # ------------------------------------------------------------
            final_output = output_path(".mp4", self.name)
            self._mux_audio_over_video(
                video_path=combined_silent,
                audio_path=narration_wav,
                output=final_output,
            )

        if not final_output.exists() or final_output.stat().st_size == 0:
            raise VideoHybridSegmentError("Final mux produced no output file.")

        cost = summarize_costs(calls, self.config.pricing)

        logger.info(
            "video_hybrid_segment: wrote %s (%d beats, %d bytes, est. cost $%.4f)",
            final_output, len(plan.beats), final_output.stat().st_size, cost["total_usd"],
        )

        return CapabilityOutput(
            file_path=final_output,
            text=plan.narration_script,
            metadata={
                "title": plan.title,
                "beat_count": len(plan.beats),
                "beat_kinds": [b.kind for b in plan.beats],
                "output_bytes": final_output.stat().st_size,
                "mime_type": "video/mp4",
                "cost": cost,
            },
        )

    # ------------------------------------------------------------------
    # Beat generators
    # ------------------------------------------------------------------

    def _generate_veo_beat(
        self, *, beat: Beat, model: str, location: str, image_bytes: bytes | None
    ) -> Path:
        try:
            result = self.client.generate_video(
                model=model,
                prompt=beat.prompt,
                duration_seconds=beat.duration_seconds,
                resolution=self._settings.get("resolution", "720p"),
                # Narration comes from a separate TTS track; let Veo stay
                # silent so there's nothing to mix against.
                generate_audio=False,
                image_bytes=image_bytes,
                image_mime_type="image/jpeg" if image_bytes else None,
                location=location,
                poll_interval_seconds=float(self._settings.get("poll_interval_seconds", 10)),
                poll_timeout_seconds=float(self._settings.get("poll_timeout_seconds", 360)),
            )
        except GeminiCallError as exc:
            raise VideoHybridSegmentError(f"Veo beat failed: {exc}") from exc

        if not result.video_bytes:
            raise VideoHybridSegmentError("Veo beat returned no video bytes.")

        clip_path = save_output(result.video_bytes, ".mp4", capability=f"{self.name}_veo")
        return clip_path

    def _generate_infographic_beat(
        self, *, beat: Beat, model: str, width: int, height: int, work: Path, index: int
    ) -> tuple[Path, Any]:
        # Nano Banana already renders text well -- this is specifically why
        # the hybrid design offloads infographics to it rather than Veo.
        # The prompt should fully specify the slide; see this file's
        # docstring and docs/VIDEO_CAPABILITIES.md for the design.
        try:
            image_result = self.client.generate_image(
                model=model,
                prompt=beat.prompt,
                resolution=self._settings.get("image_resolution", "2K"),
                output_mime_type="image/png",
            )
        except GeminiCallError as exc:
            raise VideoHybridSegmentError(f"Infographic image generation failed: {exc}") from exc
        if not image_result.image_bytes:
            raise VideoHybridSegmentError(
                "Infographic image generation returned no bytes -- likely blocked by a "
                "safety filter or the prompt was read literally. Model said: "
                f"{(image_result.text or '(no detail)').strip()[:300]}"
            )

        slide_path = work / f"beat{index}_slide.png"
        slide_path.write_bytes(image_result.image_bytes)

        # Animate the still image into a video clip: scale/pad to the
        # target resolution, then a gentle slow zoom (Ken Burns) so the
        # frame doesn't read as a static title card. Deliberately subtle
        # -- an educational slide should be comfortable to read, not
        # restless. Audio is omitted; the narration track mixes in later.
        clip_path = output_path(".mp4", f"{self.name}_infographic")
        fps = 24
        total_frames = int(beat.duration_seconds * fps)
        # zoompan needs a d= frame count; z increments per-frame so that
        # it reaches the target zoom by the last frame (feels natural,
        # not jerky).
        zoom_increment = 0.0003
        max_zoom = 1.0 + zoom_increment * total_frames  # ends slightly zoomed
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:white,"
            f"zoompan=z='min(zoom+{zoom_increment},{max_zoom:.4f})':d={total_frames}:s={width}x{height}:fps={fps}"
        )
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", str(slide_path),
            "-vf", vf,
            "-t", str(beat.duration_seconds),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(clip_path),
        ]
        logger.info("video_hybrid_segment: infographic ffmpeg: %s", " ".join(cmd))
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if proc.returncode != 0:
            stderr_tail = (proc.stderr or b"").decode("utf-8", errors="replace")[-1200:]
            raise VideoHybridSegmentError(
                f"Infographic ffmpeg animation failed (exit {proc.returncode}). "
                f"Last stderr:\n{stderr_tail}"
            )
        return clip_path, image_result.usage

    def _generate_narration(
        self, *, script: str, model: str, voice: str, work: Path
    ) -> tuple[Path, Any]:
        try:
            result = self.client.synthesize_speech(
                model=model, script=script, voice_preset=voice,
            )
        except GeminiCallError as exc:
            raise VideoHybridSegmentError(f"TTS narration call failed: {exc}") from exc
        if not result.audio_bytes:
            note = (result.text or "").strip() or "(no detail)"
            raise VideoHybridSegmentError(
                f"TTS returned no audio. Model said: {note[:300]}"
            )

        # synthesize_speech returns raw PCM; wrap as WAV (same trick
        # audio_text_to_speech capability uses).
        wav_path = work / "narration.wav"
        _write_pcm_as_wav(result.audio_bytes, wav_path, sample_rate=24000)
        return wav_path, result.usage

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    def _combine_beats(self, clip_paths: list[Path], output: Path) -> Path:
        # Delegating to the already-tested VideoCombine capability keeps
        # the timebase-sanity check (we hit a real silent-wrong-duration
        # bug against mismatched clips earlier this session; VideoCombine
        # now guards against it -- see docs/VIDEO_CAPABILITIES.md).
        from iav.capabilities.base import CapabilityInput as _CapIn
        combine = VideoCombine(config=self.config)
        combined = combine.process(_CapIn(
            file_path=clip_paths[0],
            params={"clip_paths": [str(p) for p in clip_paths[1:]]},
        ))
        # VideoCombine wrote to storage/outputs/; move to the caller's temp
        # path so this intermediate doesn't pollute the outputs dir.
        if combined.file_path and Path(combined.file_path).exists():
            shutil.copyfile(combined.file_path, output)
            Path(combined.file_path).unlink(missing_ok=True)
        else:
            raise VideoHybridSegmentError("VideoCombine did not produce a file.")
        return output

    def _mux_audio_over_video(self, *, video_path: Path, audio_path: Path, output: Path) -> None:
        # Shortest keeps the output at the video's length; if the narration
        # is shorter the tail is silent, if longer it's clipped. For a
        # well-timed script (what the caller should supply), either is
        # correct behaviour -- callers wanting exact sync should pace the
        # script to match the sum of beat durations.
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            str(output),
        ]
        logger.info("video_hybrid_segment: mux ffmpeg: %s", " ".join(cmd))
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if proc.returncode != 0:
            stderr_tail = (proc.stderr or b"").decode("utf-8", errors="replace")[-1200:]
            raise VideoHybridSegmentError(
                f"Audio mux failed (exit {proc.returncode}). "
                f"Last stderr:\n{stderr_tail}"
            )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _resolution_wh(resolution: str) -> tuple[int, int]:
    return {
        "720p": (1280, 720),
        "1080p": (1920, 1080),
    }.get(resolution, (1280, 720))


def _extract_last_frame_jpeg(video_path: Path, out_path: Path) -> bytes:
    cmd = [
        "ffmpeg", "-y", "-sseof", "-1", "-i", str(video_path),
        "-frames:v", "1", "-update", "1", "-q:v", "2", str(out_path),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0 or not out_path.exists():
        raise VideoHybridSegmentError(
            f"Last-frame extract failed (exit {proc.returncode}). "
            f"stderr tail: {(proc.stderr or b'').decode('utf-8', errors='replace')[-600:]}"
        )
    return out_path.read_bytes()


def _write_pcm_as_wav(pcm_bytes: bytes, out_path: Path, *, sample_rate: int = 24000) -> None:
    import wave
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
