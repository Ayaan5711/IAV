"""T1d: slide chain via edit_image + visual xfade during lead-in.

User feedback on T1c-nbpro: "audio is in sync but the images are
just jumping between different images, no animation." That's the
cost of hard cuts between independent Nano Banana generations --
each generation drifts slightly in layout, so the cuts read as
"different image" rather than "same slide with one new element".

Fix:
  1. Generate slide 1 fresh with Nano Banana Pro.
  2. For slides 2, 3, 4, use edit_image on the previous slide with
     a "keep everything exactly as is, only change X" instruction.
     Each slide differs from its predecessor by one card only.
  3. Build each sub-shot as a video clip of its slide, muxed with
     narration + lead-in + tail (same as T1c).
  4. Concat sub-shots with a VISUAL xfade of 0.3s overlapping the
     lead-in silence of the next sub-shot. Audio stays hard-cut --
     no acrossfade. The fade reads as "the new card fades in"
     because only that card differs between consecutive slides.

Same 4 sub-shots as T1c. Different slide chain + concat.
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
log = logging.getLogger("t1d")

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from iav.models.gemini_client import GeminiClient
from iav.models.config import load_config
from iav.storage import output_path
from scripts.full_lesson._shared import STYLE_BASE

IMAGE_MODEL = "gemini-3-pro-image"   # Nano Banana Pro for crisp text
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"
WIDTH, HEIGHT, FPS = 1280, 720, 24
LEAD_IN = 0.3
TAIL = 0.2
XFADE = 0.3  # must be <= LEAD_IN so the visual fade hides during silence


# Slide 1 is generated fresh. Slides 2, 3, 4 are edit_image steps on
# the previous slide, so each only changes the ONE card that's
# supposed to change.
FIRST_SLIDE_PROMPT = (
    "Title at top in bold dark navy sans-serif: 'GOAL, OPTION, "
    "CRITERION'. Below the title, three rounded rectangular card "
    "OUTLINES side-by-side (just the outline, empty inside, in soft "
    "slate-gray). Clean 16:9 landscape layout, generous white "
    "space. No labels inside the cards yet. Title and three outlines "
    "clearly positioned for a progressive reveal. Spell every word "
    "exactly as written, no typos."
)

EDIT_STEPS = [
    (
        "Fill in the LEFT card with a navy background, a white star "
        "icon, and the word 'GOAL' in white bold sans-serif centered "
        "inside the card. Keep EVERYTHING ELSE in the image exactly "
        "as is -- same title, same centre and right outlines, same "
        "layout, same background. Only the left card changes. Spell "
        "'GOAL' exactly, no typos."
    ),
    (
        "Fill in the CENTRE card with a navy background, a white "
        "circle icon, and the word 'OPTION' in white bold sans-serif "
        "centered inside the card. Keep EVERYTHING ELSE in the image "
        "exactly as is -- same title, same left card (GOAL), same "
        "right outline, same layout. Only the centre card changes. "
        "Spell 'OPTION' exactly, no typos."
    ),
    (
        "Fill in the RIGHT card with a navy background, a white "
        "checkmark icon, and the word 'CRITERION' in white bold "
        "sans-serif centered inside the card. Keep EVERYTHING ELSE "
        "in the image exactly as is -- same title, same left card "
        "(GOAL), same centre card (OPTION), same layout. Only the "
        "right card changes. Spell 'CRITERION' exactly, no typos."
    ),
]

NARRATIONS = [
    "To choose well, three ideas help.",
    "A goal is what we're trying to achieve.",
    "An option is one of the things we could pick.",
    "And a criterion is a reason to prefer one option over another.",
]


def _run(cmd: list[str], *, step: str) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg {step} failed:\n{proc.stderr.decode(errors='replace')[-800:]}")


def _probe_duration(path: Path) -> float:
    proc = subprocess.run(["ffmpeg", "-i", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", proc.stderr.decode(errors="replace"))
    if not m: raise RuntimeError(f"Could not probe {path}")
    h, mn, s = m.groups()
    return int(h)*3600 + int(mn)*60 + float(s)


def _pcm_to_wav(pcm_bytes: bytes, out: Path, sample_rate: int = 24000) -> None:
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


def generate_first_slide(client: GeminiClient, out_png: Path) -> None:
    log.info("  Nano Banana Pro: first slide (fresh generation)")
    result = client.generate_image(
        model=IMAGE_MODEL,
        prompt=f"{STYLE_BASE} {FIRST_SLIDE_PROMPT}",
        resolution="2K",
    )
    if not result.image_bytes:
        raise RuntimeError("Image model returned no bytes")
    out_png.write_bytes(result.image_bytes)


def edit_slide(client: GeminiClient, prev_png: Path, instruction: str, out_png: Path) -> None:
    log.info("  Nano Banana Pro: edit (chain from previous slide)")
    result = client.edit_image(
        model=IMAGE_MODEL,
        image_bytes=prev_png.read_bytes(),
        image_mime_type="image/png",
        instruction=f"{STYLE_BASE} {instruction}",
        resolution="2K",
    )
    if not result.image_bytes:
        raise RuntimeError("edit_image returned no bytes")
    out_png.write_bytes(result.image_bytes)


def generate_narration(client: GeminiClient, line: str, out_wav: Path) -> None:
    log.info("  TTS")
    result = client.synthesize_speech(model=TTS_MODEL, script=line, voice_preset=TTS_VOICE)
    _pcm_to_wav(result.audio_bytes, out_wav)


def make_subshot(slide_png: Path, narr_wav: Path, out_mp4: Path) -> float:
    """Sub-shot: slide held for LEAD_IN + narration + TAIL seconds.
    Audio: LEAD_IN of silence, then narration, then TAIL of silence.
    No xfade inside a sub-shot -- only between them, in concat."""
    narr_sec = _probe_duration(narr_wav)
    total = LEAD_IN + narr_sec + TAIL

    _run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(slide_png),
        "-i", str(narr_wav),
        "-filter_complex",
        f"[0:v]scale={WIDTH}:{HEIGHT},setsar=1:1[v];"
        f"[1:a]adelay={int(LEAD_IN*1000)}|{int(LEAD_IN*1000)},apad=pad_dur={TAIL}[a]",
        "-map", "[v]", "-map", "[a]",
        "-t", f"{total:.3f}",
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(out_mp4),
    ], step="make_subshot")

    return _probe_duration(out_mp4)


def concat_with_visual_xfade(
    subshot_paths: list[Path], durations: list[float], out_mp4: Path
) -> None:
    """Concat sub-shots with VISUAL xfade overlap (XFADE seconds),
    but keep AUDIO hard-cut (no acrossfade). The xfade sits inside
    the next sub-shot's LEAD_IN silence, so the visual blend happens
    while nothing is being said. Audio is a plain concat."""
    n = len(subshot_paths)
    if n < 2:
        shutil.copyfile(subshot_paths[0], out_mp4)
        return

    inputs: list[str] = []
    for p in subshot_paths:
        inputs += ["-i", str(p)]

    filter_parts: list[str] = []
    prev_v = "0:v"
    cumulative_v = durations[0]

    # Visual xfade chain
    for i in range(1, n):
        offset = cumulative_v - XFADE
        v_out = f"v{i}"
        filter_parts.append(
            f"[{prev_v}][{i}:v]xfade=transition=fade:duration={XFADE}:offset={offset:.3f}[{v_out}]"
        )
        prev_v = v_out
        cumulative_v += durations[i] - XFADE

    # Audio: plain concat, hard cuts
    audio_inputs = "".join(f"[{i}:a]" for i in range(n))
    filter_parts.append(f"{audio_inputs}concat=n={n}:v=0:a=1[aout]")

    filter_complex = ";".join(filter_parts)

    _run([
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{prev_v}]", "-map", "[aout]",
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(out_mp4),
    ], step="concat_with_visual_xfade")


def main() -> int:
    config = load_config()
    client = GeminiClient(config=config)
    workdir = Path("/tmp/t1d_beat1")
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir()

    t0 = time.perf_counter()

    # Build slide chain: slide 1 fresh, then 2/3/4 via edit_image
    slide_paths = [workdir / f"slide{i+1}.png" for i in range(4)]
    log.info("=" * 50)
    log.info("Slide 1/4 (fresh)")
    generate_first_slide(client, slide_paths[0])
    for i, instruction in enumerate(EDIT_STEPS, start=2):
        log.info("=" * 50)
        log.info("Slide %d/4 (edit chain)", i)
        edit_slide(client, slide_paths[i - 2], instruction, slide_paths[i - 1])

    # Narrations + sub-shots
    subshot_paths: list[Path] = []
    durations: list[float] = []
    for i, (slide_png, line) in enumerate(zip(slide_paths, NARRATIONS), start=1):
        log.info("=" * 50)
        log.info("Sub-shot %d/4: %r", i, line[:60])
        narr_wav = workdir / f"narr{i}.wav"
        subshot_mp4 = workdir / f"sub{i}.mp4"
        generate_narration(client, line, narr_wav)
        dur = make_subshot(slide_png, narr_wav, subshot_mp4)
        log.info("  dur=%.2fs", dur)
        subshot_paths.append(subshot_mp4)
        durations.append(dur)

    # Concat with visual xfade only
    log.info("=" * 50)
    log.info("Concatenating with visual xfade (audio hard-cut) ...")
    final = output_path(".mp4", "t1d_seg02_beat1_edit_chain_xfade")
    concat_with_visual_xfade(subshot_paths, durations, final)

    log.info("=== DONE ===")
    log.info("File: %s", final)
    log.info("Size: %d bytes", final.stat().st_size)
    log.info("Duration: %.2fs", _probe_duration(final))
    log.info("Wall-clock: %.1fs", time.perf_counter() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
