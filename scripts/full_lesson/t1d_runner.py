"""Shared T1d runner — the pattern we're validating as the production
replacement for the current animated-infographic beat.

Pattern (post-session 2026-11-26 validation work):
  - A segment is a flat list of SUB-SHOTS, each with its own slide
    description and one narration sentence.
  - Within one beat (a sub-shot where is_beat_start=False), the slide
    is built via edit_image on the previous slide -- surgical change,
    rest of the image preserved. This gives per-element visual stability.
  - The first sub-shot of each beat (is_beat_start=True) is a fresh
    Nano Banana Pro generation.
  - Each sub-shot's video: slide image + 0.3s silent lead-in + narration
    TTS + 0.2s silent tail, held constant for the full duration.
  - Within a beat, sub-shots are concatenated with a 0.3s visual
    cross-fade that overlaps the lead-in silence. Audio is hard-cut.
  - Between beats, hard cuts on both video and audio.

Known limitations:
  - edit_image can drift surrounding content sometimes. If drift is
    visible, fall back is programmatic PIL masking of a single base
    slide (not implemented here).
  - Nano Banana Pro cost: ~$0.20 per slide (fresh or edit). ~$0.84
    per 4-sub-shot beat, roughly cost-equivalent to the Omni-animated
    pattern it replaces.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from iav.models.gemini_client import GeminiClient
from iav.models.config import load_config, Config
from iav.storage import output_path

logger = logging.getLogger(__name__)


# Defaults -- tune these in one place and all segments using this
# runner move together.
DEFAULT_IMAGE_MODEL = "gemini-3-pro-image"        # Nano Banana Pro
DEFAULT_OMNI_MODEL = "gemini-omni-1.2-flash"      # Omni 1.2 Flash GA
DEFAULT_TTS_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_TTS_VOICE = "Kore"
DEFAULT_RESOLUTION = {"720p": (1280, 720), "1080p": (1920, 1080)}
FPS = 24
LEAD_IN = 0.3   # silence before narration starts in a sub-shot
TAIL = 0.2      # silence after narration ends
XFADE = 0.3     # visual cross-fade duration (within a beat only)
# Nano Banana Pro's image generation resolution label. "2K" is enough
# for 1080p video rendering; use "4K" when rendering 4K video.
IMAGE_RESOLUTION_FOR = {"720p": "2K", "1080p": "2K", "4K": "4K"}


@dataclass
class SubShot:
    """One sub-shot: slide/video + one sentence of narration.

    kind:
      "infographic"     — Nano Banana Pro slide + Ken Burns zoom. If
                          is_beat_start, a fresh generation; otherwise
                          an edit_image chain on the previous slide.
      "omni_realistic"  — Gemini Omni 1.2 Flash text_to_video. Always
                          a beat on its own (no edit chain). Fixed 10s.
    """
    slide: str                   # for infographic: slide prompt; for omni_realistic: text_to_video prompt
    narration: str               # one sentence for TTS
    is_beat_start: bool = False  # true = fresh NB Pro gen; false = edit_image on previous
    edit_instruction: Optional[str] = None  # used when kind=infographic, is_beat_start=False
    kind: str = "infographic"    # "infographic" | "omni_realistic"


@dataclass
class SegmentPlanV2:
    """A segment as a flat list of sub-shots with beat boundaries
    marked on the sub-shots themselves."""
    title: str                   # e.g. "Seg 2: Goal, option, criterion"
    sub_shots: list[SubShot]
    output_name: str             # e.g. "seg02_t1d" used in the output filename


def _run_ffmpeg(cmd: list[str], *, step: str) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        stderr_tail = proc.stderr.decode(errors="replace")[-1200:]
        raise RuntimeError(f"ffmpeg {step} failed (exit {proc.returncode}):\n{stderr_tail}")


def _probe_duration(path: Path) -> float:
    proc = subprocess.run(["ffmpeg", "-i", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", proc.stderr.decode(errors="replace"))
    if not m:
        raise RuntimeError(f"Could not probe duration of {path}")
    h, mn, s = m.groups()
    return int(h) * 3600 + int(mn) * 60 + float(s)


def _pcm_to_wav(pcm_bytes: bytes, out: Path, sample_rate: int = 24000) -> None:
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


def _generate_slide(client: GeminiClient, prompt_or_edit: str,
                    prev_slide: Optional[Path], out_png: Path,
                    image_model: str, image_resolution: str,
                    style_base: str) -> None:
    """Generate a slide. If prev_slide is provided, use edit_image;
    otherwise a fresh generation."""
    if prev_slide is None:
        result = client.generate_image(
            model=image_model,
            prompt=f"{style_base} {prompt_or_edit}",
            resolution=image_resolution,
        )
    else:
        result = client.edit_image(
            model=image_model,
            image_bytes=prev_slide.read_bytes(),
            image_mime_type="image/png",
            instruction=f"{style_base} {prompt_or_edit}",
            resolution=image_resolution,
        )
    if not result.image_bytes:
        raise RuntimeError("Image model returned no bytes")
    out_png.write_bytes(result.image_bytes)


def _generate_narration(client: GeminiClient, line: str, out_wav: Path,
                        tts_model: str, tts_voice: str) -> None:
    result = client.synthesize_speech(model=tts_model, script=line, voice_preset=tts_voice)
    _pcm_to_wav(result.audio_bytes, out_wav)


def _generate_omni_video(client: GeminiClient, prompt: str, out_mp4: Path,
                         omni_model: str) -> None:
    """Omni text_to_video. Fixed 10s output at 720p default."""
    result = client.interactions_video(
        model=omni_model,
        instruction=prompt,
        task="text_to_video",
    )
    if not result.video_bytes:
        raise RuntimeError("Omni text_to_video returned no bytes")
    out_mp4.write_bytes(result.video_bytes)


def _make_subshot(slide_png: Path, narr_wav: Path, out_mp4: Path,
                  width: int, height: int) -> float:
    """Build one sub-shot MP4 with subtle Ken Burns zoom for life."""
    narr_sec = _probe_duration(narr_wav)
    total = LEAD_IN + narr_sec + TAIL
    total_frames = int(total * FPS)

    # Ken Burns: slow zoom from 1.0 -> 1.05 over the sub-shot.
    # zoompan expects the input to be high-res; scale slightly larger
    # first so the zoom doesn't degrade resolution. z gets evaluated
    # per output frame, 'on' is the output frame index, 'd' is total.
    zoom_start = 1.0
    zoom_end = 1.05
    upscale = 2  # scale input 2x before zoompan so output stays sharp

    vfilter = (
        f"scale={width*upscale}:{height*upscale},setsar=1:1,"
        f"zoompan=z='{zoom_start}+({zoom_end}-{zoom_start})*on/{max(total_frames-1,1)}':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={total_frames}:s={width}x{height}:fps={FPS}"
    )

    _run_ffmpeg([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(slide_png),
        "-i", str(narr_wav),
        "-filter_complex",
        f"[0:v]{vfilter}[v];"
        f"[1:a]adelay={int(LEAD_IN*1000)}|{int(LEAD_IN*1000)},apad=pad_dur={TAIL}[a]",
        "-map", "[v]", "-map", "[a]",
        "-t", f"{total:.3f}",
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(out_mp4),
    ], step="make_subshot")

    return _probe_duration(out_mp4)


def _make_omni_subshot(omni_mp4: Path, narr_wav: Path, out_mp4: Path,
                       width: int, height: int) -> float:
    """Build an omni_realistic sub-shot: Omni's 10s video (audio
    stripped) + narration audio with LEAD_IN padding + TAIL padding.
    If narration exceeds 10s, extend video with last-frame hold."""
    narr_sec = _probe_duration(narr_wav)
    omni_sec = _probe_duration(omni_mp4)
    target = max(omni_sec, LEAD_IN + narr_sec + TAIL)
    v_extend = max(0.0, target - omni_sec)

    _run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(omni_mp4),
        "-i", str(narr_wav),
        "-filter_complex",
        # scale and extend video; strip Omni audio by not mapping its audio
        f"[0:v]scale={width}:{height},setsar=1:1,tpad=stop_mode=clone:stop_duration={v_extend:.3f}[v];"
        f"[1:a]adelay={int(LEAD_IN*1000)}|{int(LEAD_IN*1000)},apad=pad_dur={TAIL}[a]",
        "-map", "[v]", "-map", "[a]",
        "-t", f"{target:.3f}",
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(out_mp4),
    ], step="make_omni_subshot")

    return _probe_duration(out_mp4)


def _concat_group_with_xfade(group_paths: list[Path], group_durations: list[float],
                              out_mp4: Path, width: int, height: int) -> None:
    """Concat a GROUP of sub-shots (one beat) with 0.3s visual xfade,
    hard-cut audio."""
    n = len(group_paths)
    if n < 2:
        shutil.copyfile(group_paths[0], out_mp4)
        return

    inputs: list[str] = []
    for p in group_paths:
        inputs += ["-i", str(p)]

    filter_parts: list[str] = []
    prev_v = "0:v"
    cumulative_v = group_durations[0]

    for i in range(1, n):
        offset = cumulative_v - XFADE
        v_out = f"v{i}"
        filter_parts.append(
            f"[{prev_v}][{i}:v]xfade=transition=fade:duration={XFADE}:offset={offset:.3f}[{v_out}]"
        )
        prev_v = v_out
        cumulative_v += group_durations[i] - XFADE

    audio_inputs = "".join(f"[{i}:a]" for i in range(n))
    filter_parts.append(f"{audio_inputs}concat=n={n}:v=0:a=1[aout]")

    _run_ffmpeg([
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", f"[{prev_v}]", "-map", "[aout]",
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(out_mp4),
    ], step="concat_group")


def _concat_hard(paths: list[Path], out_mp4: Path) -> None:
    """Concat with hard cuts (no xfade). Used between beats."""
    if len(paths) == 1:
        shutil.copyfile(paths[0], out_mp4)
        return

    inputs: list[str] = []
    for p in paths:
        inputs += ["-i", str(p)]
    n = len(paths)
    # Use concat filter (re-encoding) so mixed-timebase inputs behave
    v_a = "".join(f"[{i}:v][{i}:a]" for i in range(n))
    _run_ffmpeg([
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", f"{v_a}concat=n={n}:v=1:a=1[outv][outa]",
        "-map", "[outv]", "-map", "[outa]",
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(out_mp4),
    ], step="concat_hard")


def _style_base() -> str:
    """Import STYLE_BASE lazily to avoid circular imports."""
    from scripts.full_lesson._shared import STYLE_BASE
    return STYLE_BASE


def run_segment(plan: SegmentPlanV2, *, resolution: str = "720p",
                client: Optional[GeminiClient] = None,
                config: Optional[Config] = None,
                image_model: str = DEFAULT_IMAGE_MODEL,
                omni_model: str = DEFAULT_OMNI_MODEL,
                tts_model: str = DEFAULT_TTS_MODEL,
                tts_voice: str = DEFAULT_TTS_VOICE) -> Path:
    """Build one segment under the T1d pattern. Returns the final MP4 path."""
    if config is None:
        config = load_config()
    if client is None:
        client = GeminiClient(config=config)

    width, height = DEFAULT_RESOLUTION.get(resolution, (1280, 720))
    image_resolution = IMAGE_RESOLUTION_FOR.get(resolution, "2K")
    style_base = _style_base()

    workdir = Path(f"/tmp/t1d_{plan.output_name}_{resolution}")
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir()

    t0 = time.perf_counter()

    # --- step 1: materialise the base media per sub-shot ---
    # For infographic kind: generate slide image (fresh or edit-chain).
    # For omni_realistic kind: generate 10s Omni text_to_video.
    slide_paths: list[Optional[Path]] = []    # None where kind=omni_realistic
    omni_paths: list[Optional[Path]] = []     # None where kind=infographic
    prev_slide: Optional[Path] = None
    for i, s in enumerate(plan.sub_shots, start=1):
        if s.kind == "infographic":
            slide_png = workdir / f"slide_{i:02d}.png"
            if s.is_beat_start:
                logger.info("[%s @ %s] sub-shot %d/%d: infographic FRESH (beat start)",
                            plan.output_name, resolution, i, len(plan.sub_shots))
                _generate_slide(client, s.slide, None, slide_png,
                                image_model, image_resolution, style_base)
            else:
                instruction = s.edit_instruction or s.slide
                logger.info("[%s @ %s] sub-shot %d/%d: infographic EDIT-chain",
                            plan.output_name, resolution, i, len(plan.sub_shots))
                _generate_slide(client, instruction, prev_slide, slide_png,
                                image_model, image_resolution, style_base)
            slide_paths.append(slide_png)
            omni_paths.append(None)
            prev_slide = slide_png
        elif s.kind == "omni_realistic":
            omni_mp4 = workdir / f"omni_{i:02d}.mp4"
            logger.info("[%s @ %s] sub-shot %d/%d: omni text_to_video",
                        plan.output_name, resolution, i, len(plan.sub_shots))
            _generate_omni_video(client, s.slide, omni_mp4, omni_model)
            slide_paths.append(None)
            omni_paths.append(omni_mp4)
            prev_slide = None  # reset edit chain: can't edit-chain across an omni beat
        else:
            raise ValueError(f"Unknown sub-shot kind: {s.kind!r}")

    # --- step 2: TTS every sub-shot's narration ---
    narr_paths: list[Path] = []
    for i, s in enumerate(plan.sub_shots, start=1):
        narr_wav = workdir / f"narr_{i:02d}.wav"
        logger.info("[%s @ %s] TTS %d/%d", plan.output_name, resolution,
                    i, len(plan.sub_shots))
        _generate_narration(client, s.narration, narr_wav, tts_model, tts_voice)
        narr_paths.append(narr_wav)

    # --- step 3: build sub-shot mp4s ---
    subshot_paths: list[Path] = []
    durations: list[float] = []
    for i, (s, slide_png, omni_mp4, narr_wav) in enumerate(
        zip(plan.sub_shots, slide_paths, omni_paths, narr_paths), start=1
    ):
        subshot_mp4 = workdir / f"sub_{i:02d}.mp4"
        if s.kind == "infographic":
            dur = _make_subshot(slide_png, narr_wav, subshot_mp4, width, height)
        else:  # omni_realistic
            dur = _make_omni_subshot(omni_mp4, narr_wav, subshot_mp4, width, height)
        logger.info("[%s @ %s] sub-shot %d/%d: kind=%s dur=%.2fs",
                    plan.output_name, resolution, i, len(plan.sub_shots), s.kind, dur)
        subshot_paths.append(subshot_mp4)
        durations.append(dur)

    # --- step 4: group into beats. A beat is a run of consecutive
    # sub-shots that share an edit chain -- i.e. a fresh infographic
    # beat-start followed by its edits. An omni_realistic sub-shot is
    # always its own beat.
    beats: list[list[int]] = []
    for idx, s in enumerate(plan.sub_shots):
        if s.is_beat_start or s.kind == "omni_realistic":
            beats.append([idx])
        else:
            beats[-1].append(idx)

    # --- step 5: concat each beat's sub-shots with visual xfade (or
    # just copy if a beat has a single sub-shot, e.g. omni_realistic) ---
    beat_mp4s: list[Path] = []
    for b_idx, beat_indices in enumerate(beats, start=1):
        beat_group_paths = [subshot_paths[i] for i in beat_indices]
        beat_group_durations = [durations[i] for i in beat_indices]
        beat_mp4 = workdir / f"beat_{b_idx:02d}.mp4"
        _concat_group_with_xfade(beat_group_paths, beat_group_durations,
                                 beat_mp4, width, height)
        logger.info("[%s @ %s] beat %d/%d: assembled %d sub-shots",
                    plan.output_name, resolution, b_idx, len(beats),
                    len(beat_indices))
        beat_mp4s.append(beat_mp4)

    # --- step 6: concat beats with hard cut ---
    final = output_path(".mp4", f"{plan.output_name}_{resolution}")
    _concat_hard(beat_mp4s, final)

    elapsed = time.perf_counter() - t0
    final_dur = _probe_duration(final)
    logger.info("[%s @ %s] DONE in %.1fs final_dur=%.2fs size=%d",
                plan.output_name, resolution, elapsed, final_dur,
                final.stat().st_size)
    return final
