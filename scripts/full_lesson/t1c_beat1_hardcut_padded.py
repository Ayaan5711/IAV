"""T1c: hard-cut sub-shots with lead-in silence.

T1b nailed "sync at sub-shot boundaries" but still felt timing-off,
because the 0.4s crossfade meant the visual transition was happening
DURING the audio of the previous sentence -- the new slide appeared
before the narrator was ready to describe it.

T1c: no crossfade. Each sub-shot gets a 0.3s silent lead-in (visual
settles) then the sentence TTS, then a 0.2s silent tail (breathing
room), then a hard cut to the next. This is the timing pattern of a
real explainer video: visual appears, half-beat, narrator describes
what just appeared, half-beat, cut.

Same slides + narration as T1b -- only the ffmpeg concat changes.
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
log = logging.getLogger("t1c")

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
LEAD_IN = 0.3   # silence BEFORE narration in each sub-shot
TAIL = 0.2      # silence AFTER narration before next cut


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
        raise RuntimeError(f"ffmpeg {step} failed:\n{proc.stderr.decode(errors='replace')[-800:]}")


def _probe_duration(path: Path) -> float:
    proc = subprocess.run(["ffmpeg", "-i", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", proc.stderr.decode(errors="replace"))
    if not m:
        raise RuntimeError(f"Could not probe {path}")
    h, mn, s = m.groups()
    return int(h) * 3600 + int(mn) * 60 + float(s)


def _pcm_to_wav(pcm_bytes: bytes, out: Path, sample_rate: int = 24000) -> None:
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


def generate_slide(client: GeminiClient, prompt: str, out_png: Path) -> None:
    result = client.generate_image(model=IMAGE_MODEL, prompt=f"{STYLE_BASE} {prompt}", resolution="2K")
    out_png.write_bytes(result.image_bytes)


def generate_narration(client: GeminiClient, line: str, out_wav: Path) -> None:
    result = client.synthesize_speech(model=TTS_MODEL, script=line, voice_preset=TTS_VOICE)
    _pcm_to_wav(result.audio_bytes, out_wav)


def make_padded_subshot(slide_png: Path, narr_wav: Path, out_mp4: Path) -> float:
    """Sub-shot: slide held for LEAD_IN + narration + TAIL seconds.
    Audio: LEAD_IN of silence, then narration, then TAIL of silence.
    Visual: slide held constant. No motion within the sub-shot itself."""
    narr_sec = _probe_duration(narr_wav)
    total = LEAD_IN + narr_sec + TAIL

    _run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(slide_png),
        "-i", str(narr_wav),
        "-filter_complex",
        f"[0:v]scale={WIDTH}:{HEIGHT},setsar=1:1[v];"
        # Pad narration with LEAD_IN of silence at the front, TAIL at the end
        f"[1:a]adelay={int(LEAD_IN*1000)}|{int(LEAD_IN*1000)},apad=pad_dur={TAIL}[a]",
        "-map", "[v]", "-map", "[a]",
        "-t", f"{total:.3f}",
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(out_mp4),
    ], step="make_padded_subshot")

    return _probe_duration(out_mp4)


def main() -> int:
    config = load_config()
    client = GeminiClient(config=config)
    workdir = Path("/tmp/t1c_beat1")
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir()

    t0 = time.perf_counter()
    subshot_paths: list[Path] = []

    for i, s in enumerate(SUBSHOTS, start=1):
        log.info("=" * 50)
        log.info("Sub-shot %d/%d: %r", i, len(SUBSHOTS), s["narration"][:60])
        slide_png = workdir / f"sub{i}_slide.png"
        narr_wav = workdir / f"sub{i}_narr.wav"
        subshot_mp4 = workdir / f"sub{i}_shot.mp4"

        log.info("  Nano Banana slide ...")
        generate_slide(client, s["slide"], slide_png)
        log.info("  TTS narration ...")
        generate_narration(client, s["narration"], narr_wav)
        log.info("  padded sub-shot ...")
        dur = make_padded_subshot(slide_png, narr_wav, subshot_mp4)
        log.info("  dur=%.2fs (narration=%.2fs, pads=%.2fs)",
                 dur, dur - LEAD_IN - TAIL, LEAD_IN + TAIL)
        subshot_paths.append(subshot_mp4)

    log.info("=" * 50)
    log.info("Hard-cut concatenating %d sub-shots ...", len(subshot_paths))
    combine = VideoCombine(config=config)
    combined = combine.process(CapabilityInput(
        file_path=subshot_paths[0],
        params={"clip_paths": [str(p) for p in subshot_paths[1:]]},
    ))

    final = output_path(".mp4", "t1c_seg02_beat1_hardcut_padded")
    shutil.copyfile(combined.file_path, final)
    Path(combined.file_path).unlink(missing_ok=True)

    log.info("")
    log.info("=== DONE ===")
    log.info("File: %s", final)
    log.info("Size: %d bytes", final.stat().st_size)
    log.info("Duration: %.2fs", _probe_duration(final))
    log.info("Wall-clock: %.1fs", time.perf_counter() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
