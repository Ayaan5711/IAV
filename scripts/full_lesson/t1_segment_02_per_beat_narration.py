"""T1: per-beat narration sync test — segment 2 rebuild.

Purpose: validate whether per-beat TTS + per-beat mux-before-concat
solves the sync/drift problem in the current pipeline (one TTS call
per segment, muxed over the pre-stitched video). This is a one-off
standalone script so the main pipeline stays untouched.

Approach per beat:
  1. Nano Banana renders the slide still image
  2. ffmpeg loops it into a 10s silent video
  3. Omni edit animates the elements
  4. TTS voices ONLY this beat's narration line
  5. Measure narration duration
  6. Strip Omni's audio, pad or extend video to narration length,
     mux narration in — this is the sync point.
  7. Append muxed beat to the concat list.

Final: concat the muxed beats. By construction each beat's
narration is exactly in sync with its own video. No cross-beat drift
is possible.

If this comes back feeling tighter than Run B's segment 2, the fix
is the right one and we promote it into the main capability.
"""
import logging
import re
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("t1-seg2")

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from iav.models.gemini_client import GeminiClient
from iav.models.config import load_config
from iav.capabilities.video_combine import VideoCombine
from iav.capabilities.base import CapabilityInput
from iav.storage import output_path
from scripts.full_lesson._shared import STYLE_BASE, ANIMATE_PRESERVE


# Models — same as the main pipeline
OMNI_MODEL = "gemini-omni-1.2-flash"
IMAGE_MODEL = "gemini-3.1-flash-image"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"

WIDTH, HEIGHT, FPS = 1280, 720, 24
BEAT_SECS = 10


# Segment 2's three beats — same visual prompts as production, but
# the narration is split per-beat here so each line maps to its slide.
BEATS = [
    {
        "slide": (
            "Title at top in bold dark navy: 'GOAL, OPTION, CRITERION'. Below, "
            "three rounded rectangular cards side-by-side, labelled in large "
            "clean sans-serif: 'GOAL' (left card, with a small star icon), "
            "'OPTION' (centre card, with a small circle icon), 'CRITERION' "
            "(right card, with a small checkmark icon)."
        ),
        "animate": (
            "Animate: the three labelled cards appear one after another, GOAL "
            "first, then OPTION, then CRITERION. Each card slides into "
            "position from below with a gentle ease. Final state: all three "
            "cards visible, evenly spaced across the middle of the slide."
        ),
        "narration": (
            "To choose well, three ideas help. A goal is what we're trying to "
            "achieve. An option is one of the things we could pick. And a "
            "criterion is a reason to prefer one option over another."
        ),
    },
    {
        "slide": (
            "Title at top: 'THE GOAL SHAPES THE CRITERIA'. In the centre, a "
            "navy star icon labelled 'GOAL: a warm weekend trip' at the top. "
            "A navy arrow points down from the star to three smaller rounded "
            "rectangular labels in a row below: 'warm clothes', 'lightweight "
            "bag', 'good shoes'. All labels in clean sans-serif, navy on white."
        ),
        "animate": (
            "Animate: the GOAL star appears first at top, holds for a moment, "
            "then an arrow draws downward, and the three criterion labels "
            "appear from left to right in sequence under the arrow."
        ),
        "narration": (
            "Here's the important link: the goal shapes the criteria. If the "
            "goal is a warm weekend trip, we look for warm clothes, a "
            "lightweight bag, good shoes."
        ),
    },
    {
        "slide": (
            "Title at top: 'DIFFERENT GOAL, DIFFERENT CRITERIA'. In the "
            "centre: a navy mountain icon labelled 'GOAL: a winter hike' at "
            "the top. A navy arrow points down to three rounded rectangular "
            "labels: 'insulated jacket', 'waterproof boots', 'thermal flask'. "
            "Clean, consistent style with the previous slide."
        ),
        "animate": (
            "Animate: the GOAL mountain icon appears first, holds briefly, "
            "then the arrow draws down and the three new criterion labels "
            "appear from left to right."
        ),
        "narration": (
            "But change the goal to a winter hike, and the criteria change "
            "too: now we need insulated layers, waterproof boots, a thermal "
            "flask. Same person, different goal, different criteria."
        ),
    },
]


def _run(cmd: list[str], *, step: str) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        stderr_tail = proc.stderr.decode(errors="replace")[-800:]
        raise RuntimeError(f"ffmpeg {step} failed:\n{stderr_tail}")


def _probe_duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffmpeg", "-i", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    text = proc.stderr.decode(errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", text)
    if not m:
        raise RuntimeError(f"Could not probe duration of {path}")
    h, mn, s = m.groups()
    return int(h) * 3600 + int(mn) * 60 + float(s)


def _pcm_to_wav(pcm_bytes: bytes, out: Path, sample_rate: int = 24000) -> None:
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


def generate_slide(client: GeminiClient, prompt: str, out_png: Path) -> None:
    full_prompt = f"{STYLE_BASE} {prompt}"
    log.info("  Nano Banana slide ...")
    result = client.generate_image(
        model=IMAGE_MODEL, prompt=full_prompt, resolution="2K",
    )
    if not result.image_bytes:
        raise RuntimeError("Nano Banana returned no image bytes")
    out_png.write_bytes(result.image_bytes)


def loop_slide_to_video(slide_png: Path, out_mp4: Path) -> None:
    _run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(slide_png),
        "-t", str(BEAT_SECS), "-r", str(FPS),
        "-vf", f"scale={WIDTH}:{HEIGHT},setsar=1:1",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-tune", "stillimage",
        "-movflags", "+faststart", str(out_mp4),
    ], step="loop_slide")


def animate_with_omni(client: GeminiClient, video_in: Path, animation_prompt: str,
                     out_mp4: Path) -> None:
    full_prompt = f"{ANIMATE_PRESERVE} {animation_prompt}"
    log.info("  Omni edit ...")
    result = client.interactions_video(
        model=OMNI_MODEL,
        instruction=full_prompt,
        task="edit",
        video_bytes=video_in.read_bytes(),
        video_mime_type="video/mp4",
    )
    if not result.video_bytes:
        raise RuntimeError("Omni edit returned no video")
    out_mp4.write_bytes(result.video_bytes)


def generate_narration(client: GeminiClient, line: str, out_wav: Path) -> None:
    log.info("  TTS narration ...")
    result = client.synthesize_speech(
        model=TTS_MODEL, script=line, voice_preset=TTS_VOICE,
    )
    if not result.audio_bytes:
        raise RuntimeError("TTS returned no audio")
    _pcm_to_wav(result.audio_bytes, out_wav)


def mux_beat(animated_mp4: Path, narration_wav: Path, out_mp4: Path) -> None:
    """Per-beat mux. Strips Omni's audio, mixes in narration. If
    narration is longer than 10s, extends the video by holding the
    last frame. If narration is shorter, pads silence at the end.
    Either way: beat video length EQUALS narration length (plus any
    silent tail from the apad)."""
    narr_sec = _probe_duration(narration_wav)
    vid_sec = _probe_duration(animated_mp4)
    target = max(narr_sec, vid_sec)
    log.info("  narration=%.2fs  video=%.2fs  target=%.2fs", narr_sec, vid_sec, target)

    # Extend the video via tpad (last-frame freeze) if narration is
    # longer than the beat's natural 10s. Pad the narration with
    # silence via apad to match the final length.
    v_extend = max(0.0, target - vid_sec)
    _run([
        "ffmpeg", "-y",
        "-i", str(animated_mp4), "-i", str(narration_wav),
        "-filter_complex",
        # video: hold last frame if needed; audio: apad to target
        f"[0:v]tpad=stop_mode=clone:stop_duration={v_extend}[v];"
        f"[1:a]apad[a]",
        "-map", "[v]", "-map", "[a]",
        "-t", f"{target:.3f}",  # hard-cap the whole beat at target
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-r", str(FPS), "-movflags", "+faststart",
        str(out_mp4),
    ], step="mux_beat")


def main() -> int:
    config = load_config()
    client = GeminiClient(config=config)
    workdir = Path("/tmp/t1_seg2_per_beat_narration")
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir()

    t_start = time.perf_counter()
    muxed_beats: list[Path] = []

    for i, beat in enumerate(BEATS, start=1):
        log.info("=" * 60)
        log.info("Beat %d/%d", i, len(BEATS))
        log.info("=" * 60)

        slide_png = workdir / f"beat{i}_slide.png"
        loop_mp4 = workdir / f"beat{i}_loop.mp4"
        anim_mp4 = workdir / f"beat{i}_anim.mp4"
        narr_wav = workdir / f"beat{i}_narr.wav"
        muxed_mp4 = workdir / f"beat{i}_muxed.mp4"

        generate_slide(client, beat["slide"], slide_png)
        loop_slide_to_video(slide_png, loop_mp4)
        animate_with_omni(client, loop_mp4, beat["animate"], anim_mp4)
        generate_narration(client, beat["narration"], narr_wav)
        mux_beat(anim_mp4, narr_wav, muxed_mp4)

        muxed_beats.append(muxed_mp4)

    # Concat the three muxed beats
    log.info("=" * 60)
    log.info("Concatenating %d muxed beats ...", len(muxed_beats))
    log.info("=" * 60)
    combine = VideoCombine(config=config)
    combined = combine.process(CapabilityInput(
        file_path=muxed_beats[0],
        params={"clip_paths": [str(p) for p in muxed_beats[1:]]},
    ))

    # Move to a stable named output
    final = output_path(".mp4", "t1_seg02_per_beat_narration")
    shutil.copyfile(combined.file_path, final)
    Path(combined.file_path).unlink(missing_ok=True)

    final_dur = _probe_duration(final)
    log.info("")
    log.info("=== DONE ===")
    log.info("File: %s", final)
    log.info("Size: %d bytes", final.stat().st_size)
    log.info("Duration: %.2fs", final_dur)
    log.info("Wall-clock: %.1fs", time.perf_counter() - t_start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
