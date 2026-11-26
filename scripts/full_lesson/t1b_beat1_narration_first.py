"""T1b: narration-first, visuals-timed-to-it — segment 2 beat 1 only.

Per-beat narration (T1) fixed the beat-level overflow but not the
intra-beat drift between narration words and Omni's animation
timing. Omni is a black box for element reveal timing; we can't
schedule it. Fix: don't ask Omni to animate at all within a beat.
Instead, break each beat into one SUB-SHOT per narration sentence.
Each sub-shot is a Nano Banana slide showing exactly what's revealed
at that line, held for exactly that sentence's TTS duration.
Cross-fade transitions between sub-shots give the eye the progressive-
reveal feel without needing Omni to invent timing.

For this test: segment 2 beat 1 ONLY (the GOAL/OPTION/CRITERION
cards). If the sync feels right, we'll scale up.
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
log = logging.getLogger("t1b-seg2-beat1")

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from iav.models.gemini_client import GeminiClient
from iav.models.config import load_config
from iav.capabilities.video_combine import VideoCombine
from iav.capabilities.base import CapabilityInput
from iav.storage import output_path
from scripts.full_lesson._shared import STYLE_BASE


IMAGE_MODEL = "gemini-3.1-flash-image"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"
WIDTH, HEIGHT, FPS = 1280, 720, 24
CROSSFADE_DURATION = 0.4  # seconds


# Beat 1 of segment 2, decomposed into 4 sub-shots -- one per
# narration sentence. The slide descriptions reveal elements in
# the order the narrator mentions them, so each word lands on the
# right visual.
SUBSHOTS = [
    {
        "narration": "To choose well, three ideas help.",
        "slide": (
            "Title at top in bold dark navy sans-serif: 'GOAL, OPTION, "
            "CRITERION'. Below the title, three rounded rectangular card "
            "OUTLINES side-by-side (just the outline, empty inside, in soft "
            "slate-gray). Clean 16:9 landscape layout, generous white "
            "space. No labels inside the cards yet."
        ),
    },
    {
        "narration": "A goal is what we're trying to achieve.",
        "slide": (
            "Title at top in bold dark navy sans-serif: 'GOAL, OPTION, "
            "CRITERION'. Below the title, three rounded rectangular cards "
            "side-by-side. The LEFT card is filled in navy with a white "
            "star icon and the word 'GOAL' in white bold sans-serif. The "
            "centre and right cards are still slate-gray outlines, empty. "
            "Clean 16:9 landscape layout."
        ),
    },
    {
        "narration": "An option is one of the things we could pick.",
        "slide": (
            "Title at top in bold dark navy sans-serif: 'GOAL, OPTION, "
            "CRITERION'. Below, three rounded rectangular cards. LEFT card: "
            "filled navy, white star icon, white bold 'GOAL' label. CENTRE "
            "card: filled navy, white circle icon, white bold 'OPTION' "
            "label. RIGHT card: still a slate-gray outline, empty. Clean "
            "16:9 landscape."
        ),
    },
    {
        "narration": "And a criterion is a reason to prefer one option over another.",
        "slide": (
            "Title at top in bold dark navy sans-serif: 'GOAL, OPTION, "
            "CRITERION'. Below, three rounded rectangular cards, all three "
            "filled in navy with white icons and white bold labels: 'GOAL' "
            "with a star (left), 'OPTION' with a circle (centre), "
            "'CRITERION' with a checkmark (right). Clean 16:9 landscape, "
            "evenly spaced."
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
    result = client.generate_image(
        model=IMAGE_MODEL,
        prompt=f"{STYLE_BASE} {prompt}",
        resolution="2K",
    )
    if not result.image_bytes:
        raise RuntimeError("Nano Banana returned no image bytes")
    out_png.write_bytes(result.image_bytes)


def generate_narration(client: GeminiClient, line: str, out_wav: Path) -> None:
    result = client.synthesize_speech(
        model=TTS_MODEL, script=line, voice_preset=TTS_VOICE,
    )
    if not result.audio_bytes:
        raise RuntimeError("TTS returned no audio")
    _pcm_to_wav(result.audio_bytes, out_wav)


def make_subshot(slide_png: Path, narr_wav: Path, out_mp4: Path) -> float:
    """Build a sub-shot: slide held for narration's full duration, with
    the narration audio muxed in. Returns the sub-shot's duration."""
    narr_sec = _probe_duration(narr_wav)
    # Add a small tail so audio tails don't clip
    hold_sec = narr_sec + 0.15

    _run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(slide_png),
        "-i", str(narr_wav),
        "-filter_complex",
        f"[0:v]scale={WIDTH}:{HEIGHT},setsar=1:1,tpad=stop_duration=0.15:stop_mode=clone[v];"
        f"[1:a]apad=pad_dur=0.15[a]",
        "-map", "[v]", "-map", "[a]",
        "-t", f"{hold_sec:.3f}",
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(out_mp4),
    ], step="make_subshot")

    return _probe_duration(out_mp4)


def crossfade_concat(subshots: list[Path], durations: list[float], out_mp4: Path) -> None:
    """Concat sub-shots with a short xfade crossfade between each pair.
    Using the xfade filter instead of a plain concat gives a visual
    transition that reads as motion without needing Omni."""
    n = len(subshots)
    if n < 2:
        shutil.copyfile(subshots[0], out_mp4)
        return

    inputs: list[str] = []
    for p in subshots:
        inputs += ["-i", str(p)]

    # Build the filter graph. For N clips, we need N-1 xfades.
    # xfade offset = (duration of all previous clips up to this one) - crossfade_duration
    filter_parts: list[str] = []
    prev_v = "0:v"
    prev_a = "0:a"
    cumulative = durations[0]

    for i in range(1, n):
        offset = cumulative - CROSSFADE_DURATION
        v_out = f"v{i}"
        a_out = f"a{i}"
        filter_parts.append(
            f"[{prev_v}][{i}:v]xfade=transition=fade:duration={CROSSFADE_DURATION}:offset={offset:.3f}[{v_out}]"
        )
        filter_parts.append(
            f"[{prev_a}][{i}:a]acrossfade=d={CROSSFADE_DURATION}[{a_out}]"
        )
        prev_v = v_out
        prev_a = a_out
        cumulative += durations[i] - CROSSFADE_DURATION

    filter_complex = ";".join(filter_parts)

    _run([
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{prev_v}]", "-map", f"[{prev_a}]",
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(out_mp4),
    ], step="crossfade_concat")


def main() -> int:
    config = load_config()
    client = GeminiClient(config=config)

    workdir = Path("/tmp/t1b_beat1")
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir()

    t_start = time.perf_counter()
    subshot_paths: list[Path] = []
    subshot_durations: list[float] = []

    for i, s in enumerate(SUBSHOTS, start=1):
        log.info("=" * 60)
        log.info("Sub-shot %d/%d: %r", i, len(SUBSHOTS), s["narration"][:50])
        log.info("=" * 60)

        slide_png = workdir / f"sub{i}_slide.png"
        narr_wav = workdir / f"sub{i}_narr.wav"
        subshot_mp4 = workdir / f"sub{i}_shot.mp4"

        log.info("  Nano Banana slide ...")
        generate_slide(client, s["slide"], slide_png)
        log.info("  TTS narration ...")
        generate_narration(client, s["narration"], narr_wav)
        log.info("  make sub-shot ...")
        duration = make_subshot(slide_png, narr_wav, subshot_mp4)
        log.info("  duration=%.2fs", duration)

        subshot_paths.append(subshot_mp4)
        subshot_durations.append(duration)

    log.info("=" * 60)
    log.info("Crossfade-concatenating %d sub-shots ...", len(subshot_paths))
    log.info("=" * 60)

    final = output_path(".mp4", "t1b_seg02_beat1_narration_first")
    crossfade_concat(subshot_paths, subshot_durations, final)

    final_dur = _probe_duration(final)
    log.info("")
    log.info("=== DONE ===")
    log.info("File: %s", final)
    log.info("Size: %d bytes", final.stat().st_size)
    log.info("Duration: %.2fs", final_dur)
    log.info("Wall-clock: %.1fs", time.perf_counter() - t_start)
    log.info("")
    log.info("Per-sub-shot durations:")
    for i, (s, d) in enumerate(zip(SUBSHOTS, subshot_durations), start=1):
        log.info("  %d: %.2fs  %r", i, d, s["narration"][:60])
    return 0


if __name__ == "__main__":
    sys.exit(main())
