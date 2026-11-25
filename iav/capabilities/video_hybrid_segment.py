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

    kind: str  # "veo" | "infographic" | "infographic_animated" | "omni_realistic"
    prompt: str  # scene / image / animation prompt depending on kind
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
                    # "infographic" = static Nano Banana slide + ffmpeg
                    # Ken Burns zoom. Cheap and fast. Lacks element-level
                    # motion; best for low-stakes or short beats.
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
                    last_frame_bytes = None
                elif beat.kind == "infographic_animated":
                    # "infographic_animated" = Nano Banana slide, looped as
                    # short video, then Omni edit animates the elements
                    # (live-verified 2026-11-25: elements slide, labels
                    # emerge in colour, style preserved -- real motion-
                    # graphics narrative, not zoom). Caps at 10 seconds
                    # per call (Omni edit input cap); longer beats need
                    # chaining, which the caller handles by sequencing
                    # multiple "infographic_animated" beats.
                    omni_model = (payload.params or {}).get("omni_model") or self._settings.get("omni_model", "gemini-omni-1.2-flash")
                    clip, image_usage = self._generate_animated_infographic_beat(
                        beat=beat,
                        image_model=image_model,
                        omni_model=omni_model,
                        width=width,
                        height=height,
                        work=work,
                        index=i + 1,
                    )
                    calls.append({
                        "label": f"beat{i+1}_infographic_slide",
                        "model": image_model,
                        "usage": image_usage,
                    })
                    calls.append({
                        "label": f"beat{i+1}_infographic_anim",
                        "model": omni_model,
                        "usage": None,
                        "duration_seconds": float(min(beat.duration_seconds, 10)),
                        "resolution": resolution,
                    })
                    last_frame_bytes = None
                elif beat.kind == "omni_realistic":
                    # "omni_realistic" = Omni text-to-video, replaces Veo
                    # in the pipeline after the 2026-11-25 pivot to drop
                    # Veo. Each call produces 10s at 720p; shorter target
                    # durations are rounded up by Omni itself. No frame
                    # chaining (Omni text_to_video doesn't take a seed
                    # image); merge chained pairs into a single prompt.
                    omni_model = (payload.params or {}).get("omni_model") or self._settings.get("omni_model", "gemini-omni-1.2-flash")
                    clip = self._generate_omni_realistic_beat(
                        beat=beat,
                        omni_model=omni_model,
                        work=work,
                        index=i + 1,
                    )
                    calls.append({
                        "label": f"beat{i+1}_omni_realistic",
                        "model": omni_model,
                        "usage": None,
                        "duration_seconds": float(min(beat.duration_seconds, 10)),
                        "resolution": resolution,
                    })
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

    def _generate_omni_realistic_beat(
        self, *, beat: Beat, omni_model: str, work: Path, index: int
    ) -> Path:
        """Omni text-to-video for realistic/cinematic beats (Veo replacement).

        Omni outputs a fixed 10s clip per call at 720p -- duration_seconds
        on the beat is advisory only. No image conditioning (Omni's
        text_to_video mode takes a prompt only); callers wanting shot
        continuity across beats should merge them into a single prompt.
        """
        try:
            result = self.client.interactions_video(
                model=omni_model,
                instruction=beat.prompt,
                task="text_to_video",
            )
        except GeminiCallError as exc:
            raise VideoHybridSegmentError(
                f"Omni realistic beat {index} failed: {exc}"
            ) from exc

        if not result.video_bytes:
            raise VideoHybridSegmentError(
                f"Omni realistic beat {index} returned no video bytes."
            )

        clip_path = output_path(".mp4", f"{self.name}_omni_realistic")
        clip_path.write_bytes(result.video_bytes)
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

    def _generate_animated_infographic_beat(
        self, *, beat: Beat, image_model: str, omni_model: str,
        width: int, height: int, work: Path, index: int,
    ) -> tuple[Path, Any]:
        """Two-stage: Nano Banana renders the crisp base slide, Omni edit
        animates the elements. Preserves Nano Banana's text/geometry
        quality (Veo can't) while adding real element-level motion
        (Ken Burns can't). Beat duration is clamped to Omni's 10-second
        input/output cap -- callers wanting longer sequences chain
        multiple beats.

        Beat prompt is a two-section string split by '::ANIMATE::' --
        everything before is the Nano Banana slide prompt, everything
        after is the Omni edit animation instruction. This keeps a
        single prompt field per beat while letting the author write
        both halves cleanly.
        """
        if "::ANIMATE::" not in beat.prompt:
            raise VideoHybridSegmentError(
                "infographic_animated beat requires beat.prompt to contain "
                "'::ANIMATE::' separating the slide prompt from the "
                "animation instruction. Got: " + beat.prompt[:120]
            )
        slide_prompt, _, animate_instruction = beat.prompt.partition("::ANIMATE::")
        slide_prompt = slide_prompt.strip()
        animate_instruction = animate_instruction.strip()

        duration = min(int(beat.duration_seconds), 10)  # Omni edit hard cap
        if duration != beat.duration_seconds:
            logger.warning(
                "infographic_animated beat %d: clamping duration %ds -> %ds "
                "(Omni edit input cap)",
                index, beat.duration_seconds, duration,
            )

        # Stage 1: Nano Banana generates the base slide
        try:
            image_result = self.client.generate_image(
                model=image_model,
                prompt=slide_prompt,
                resolution=self._settings.get("image_resolution", "2K"),
                output_mime_type="image/png",
            )
        except GeminiCallError as exc:
            raise VideoHybridSegmentError(f"Infographic base slide generation failed: {exc}") from exc
        if not image_result.image_bytes:
            raise VideoHybridSegmentError(
                "Infographic base slide returned no bytes -- likely blocked by a safety "
                f"filter. Model said: {(image_result.text or '(no detail)').strip()[:300]}"
            )
        slide_path = work / f"beat{index}_slide.png"
        slide_path.write_bytes(image_result.image_bytes)

        # Stage 2: loop the slide as a short video for Omni edit input
        loop_path = work / f"beat{index}_loop.mp4"
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", str(slide_path),
            "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:white,fps=24",
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", str(loop_path),
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if proc.returncode != 0:
            stderr_tail = (proc.stderr or b"").decode("utf-8", errors="replace")[-800:]
            raise VideoHybridSegmentError(
                f"Infographic slide-loop ffmpeg failed (exit {proc.returncode}): {stderr_tail}"
            )

        # Stage 3: Omni edit animates the elements
        try:
            omni_result = self.client.interactions_video(
                model=omni_model,
                task="edit",
                video_bytes=loop_path.read_bytes(),
                video_mime_type="video/mp4",
                instruction=animate_instruction,
            )
        except GeminiCallError as exc:
            raise VideoHybridSegmentError(f"Infographic Omni-edit animation failed: {exc}") from exc
        if not omni_result.video_bytes:
            raise VideoHybridSegmentError("Omni edit returned no video bytes for infographic beat.")

        clip_path = output_path(".mp4", f"{self.name}_infographic_anim")
        clip_path.write_bytes(omni_result.video_bytes)
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
        # Normalize: strip audio from every beat before concat. Beats can
        # arrive with or without audio depending on the generator (Veo
        # with generate_audio=False is silent; Omni edit always carries
        # an audio stream in its output). VideoCombine's re-encode concat
        # path uses `concat=n=N:v=1:a=1` which requires audio on every
        # input -- mixing silent and audio-carrying clips makes it fail
        # with "Stream specifier ':a:0' matches no streams". The hybrid
        # capability always mutes the base video then mixes narration
        # over the top in _mux_audio_over_video(), so dropping beat
        # audio here is both correct and necessary.
        from iav.capabilities.base import CapabilityInput as _CapIn
        work_dir = output.parent
        stripped_paths: list[Path] = []
        for i, src in enumerate(clip_paths):
            stripped = work_dir / f"beat{i+1}_noaudio.mp4"
            cmd = [
                "ffmpeg", "-y", "-i", str(src),
                "-an",  # drop audio
                "-c:v", "copy",
                "-movflags", "+faststart",
                str(stripped),
            ]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if proc.returncode != 0:
                stderr_tail = (proc.stderr or b"").decode("utf-8", errors="replace")[-600:]
                raise VideoHybridSegmentError(
                    f"audio-strip ffmpeg failed on beat {i+1} (exit {proc.returncode}): {stderr_tail}"
                )
            stripped_paths.append(stripped)

        combine = VideoCombine(config=self.config)
        combined = combine.process(_CapIn(
            file_path=stripped_paths[0],
            params={"clip_paths": [str(p) for p in stripped_paths[1:]]},
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
        # Pad narration with silence to match video length -- deliberately
        # NOT using -shortest here. First build caught this: a 54-second
        # narration against a 64-second combined video with -shortest
        # silently clipped 10 seconds off the ending (the final Veo beat's
        # payoff shot got cut mid-action). A silent tail is the right
        # default for teaching video -- lets the viewer absorb a closing
        # beat without voice-over, which is a normal production choice;
        # a clipped ending is just a bug. Callers wanting the audio to
        # cover every frame should pace their narration to match the sum
        # of beat durations.
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-filter_complex", "[1:a]apad[padded]",
            "-map", "0:v:0", "-map", "[padded]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",  # with apad on the audio, this now means "match video length"
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
