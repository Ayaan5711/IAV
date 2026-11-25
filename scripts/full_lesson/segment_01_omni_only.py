"""Segment 1 regenerated with Omni ONLY (no Veo, no Nano Banana).

Purpose: answer Sharmila di's question -- can one model (Gemini Omni)
produce everything the hybrid pipeline currently does? This script keeps
the narration script and the four-beat structure identical to the real
segment 1, swaps every beat to Omni text-to-video, then stitches and
mutes under the same TTS narration. Output goes alongside the real
segment 1 so they can be viewed side by side.
"""
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("omni-only-seg1")

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from iav.models.gemini_client import GeminiClient
from iav.models.config import load_config
from iav.capabilities.video_combine import VideoCombine
from iav.capabilities.base import CapabilityInput
from iav.storage import output_path


OMNI_MODEL = "gemini-omni-1.1-flash-preview"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"

# Same four beats as segment_01_everyday.py, same wording, but every one
# goes to Omni text_to_video. (Omni caps at ~10s/output so the 8s beats
# round up to 10s -- segment runs ~40s instead of 34s, close enough to
# compare like-for-like with the hybrid output.)
BEAT_PROMPTS = [
    "A woman in her thirties stands in a grocery store aisle holding two "
    "different boxes of cookies, one in each hand, comparing them "
    "thoughtfully. Bright warm indoor lighting. Realistic footage.",

    "The same woman smiles, places one box into her shopping cart, and "
    "pushes the cart down the aisle. Bright warm indoor lighting. "
    "Realistic footage.",

    "A man in his thirties at a modern car dealership looking between "
    "two different cars (one silver sedan, one blue compact SUV) parked "
    "side by side. Soft natural lighting through large windows. "
    "Realistic footage.",

    "Clean professional educational infographic slide, flat 2D design "
    "style. Title at top in bold dark navy sans-serif: 'EVERY DAY, WE "
    "CHOOSE'. Below the title, three equally-sized cards in a row, each "
    "with a simple flat illustration: left card shows a shopping basket "
    "with cookies, middle card shows a car silhouette, right card shows "
    "a signpost at a fork in a path. Each card has a short slate-gray "
    "caption underneath: 'What to buy', 'What to drive', 'Which way to "
    "go'. Animate: the three cards fade in one after another from left "
    "to right (shopping basket first, then car, then signpost), each "
    "landing with a gentle bounce. The title stays stable throughout.",
]

NARRATION = (
    "Every day, we make choices. Which box of cookies to buy. Which car fits "
    "the family. Which direction to take in life. These look like very "
    "different decisions. But they share the same shape: we have options, and "
    "we have reasons to prefer one over the others. That is what selection "
    "is -- not just picking, but picking for a reason."
)


def _strip_audio(src: Path, dst: Path) -> None:
    cmd = ["ffmpeg", "-y", "-i", str(src), "-an", "-c:v", "copy",
           "-movflags", "+faststart", str(dst)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg -an failed:\n{proc.stderr.decode(errors='replace')[-600:]}")


def _mux(video: Path, audio: Path, out: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video), "-i", str(audio),
        "-filter_complex", "[1:a]apad[padded]",
        "-map", "0:v:0", "-map", "[padded]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", str(out),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg mux failed:\n{proc.stderr.decode(errors='replace')[-600:]}")


def _pcm_to_wav(pcm_bytes: bytes, out: Path, sample_rate: int = 24000) -> None:
    import wave
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


def main() -> int:
    config = load_config()
    client = GeminiClient(config=config)

    workdir = Path("/tmp/omni_only_seg1")
    workdir.mkdir(exist_ok=True)

    beat_paths: list[Path] = []
    t_start = time.perf_counter()

    for i, prompt in enumerate(BEAT_PROMPTS, start=1):
        log.info("=" * 50)
        log.info("Beat %d/%d: calling Omni text_to_video", i, len(BEAT_PROMPTS))
        t0 = time.perf_counter()
        try:
            result = client.interactions_video(
                model=OMNI_MODEL,
                instruction=prompt,
                task="text_to_video",
            )
        except Exception as e:
            log.exception("Beat %d failed: %s", i, e)
            raise
        clip_path = workdir / f"beat{i}.mp4"
        clip_path.write_bytes(result.video_bytes)
        log.info("  beat %d OK (%d bytes, %.1fs wall)", i, len(result.video_bytes),
                 time.perf_counter() - t0)
        # Strip audio immediately so concat is uniform.
        stripped = workdir / f"beat{i}_noaudio.mp4"
        _strip_audio(clip_path, stripped)
        beat_paths.append(stripped)

    log.info("All 4 beats generated in %.1fs", time.perf_counter() - t_start)

    # Narration
    log.info("Generating TTS narration ...")
    tts_result = client.synthesize_speech(
        model=TTS_MODEL, script=NARRATION, voice_preset=TTS_VOICE,
    )
    wav_path = workdir / "narration.wav"
    _pcm_to_wav(tts_result.audio_bytes, wav_path)

    # Combine
    log.info("Concatenating beats ...")
    combine = VideoCombine(config=config)
    combined_result = combine.process(CapabilityInput(
        file_path=beat_paths[0],
        params={"clip_paths": [str(p) for p in beat_paths[1:]]},
    ))
    combined_silent = workdir / "combined_silent.mp4"
    shutil.copyfile(combined_result.file_path, combined_silent)
    Path(combined_result.file_path).unlink(missing_ok=True)

    # Mux
    final = output_path(".mp4", "segment_01_OMNI_ONLY")
    _mux(combined_silent, wav_path, final)

    # Duration probe
    probe = subprocess.run(
        ["ffmpeg", "-i", str(final)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    import re
    m = re.search(r"Duration: (\d+:\d+:\d+\.\d+)", probe.stderr.decode(errors="replace"))
    log.info("")
    log.info("=== DONE ===")
    log.info("File: %s", final)
    log.info("Size: %d bytes", final.stat().st_size)
    log.info("Duration: %s", m.group(1) if m else "?")
    log.info("Total wall: %.1fs", time.perf_counter() - t_start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
