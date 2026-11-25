"""Run every Selection Criterion segment, assemble the final 15-minute MP4.

Executes segments 1-3, 5-11 sequentially (segment 4 was already built
and that MP4 is reused as-is to save time and money). Each segment's
output path is captured; at the end they're all concatenated with
video_combine into one final lesson video.

Progress is logged to progress.log so we can watch it from another
shell while it runs.
"""
import importlib
import logging
import shutil
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("/tmp/claude-0/-home-user-IAV/e9b40bb4-f11e-517f-8664-695af61234e2/scratchpad/full_lesson_progress.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("full-lesson")

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from iav.capabilities.video_hybrid_segment import VideoHybridSegment
from iav.capabilities.video_combine import VideoCombine
from iav.capabilities.base import CapabilityInput
from iav.storage import output_path


# Segment 4 is already built; everything else gets generated now.
SEGMENT_4_PREBUILT = Path("/home/user/IAV/storage/outputs/video_hybrid_segment-20261125T082431Z-400272c4.mp4")
assert SEGMENT_4_PREBUILT.exists(), f"missing: {SEGMENT_4_PREBUILT}"

SEGMENT_ORDER = [
    "segment_01_everyday",
    "segment_02_what_are_criteria",
    "segment_03_need_constraints",
    None,  # segment 4 slot, reuse SEGMENT_4_PREBUILT
    "segment_05_hard_soft",
    "segment_06_priorities_tradeoffs",
    "segment_07_process",
    "segment_08_crossroads",
    "segment_09_mistakes",
    "segment_10_metrics",
    "segment_11_recap",
]


def run_segment(mod_name: str) -> Path:
    log.info("=" * 60)
    log.info(f"Running {mod_name}")
    log.info("=" * 60)
    t0 = time.perf_counter()
    mod = importlib.import_module(f"scripts.full_lesson.{mod_name}")
    plan = mod.PLAN
    cap = VideoHybridSegment()
    result = cap.process(CapabilityInput(params={"plan": plan}))
    elapsed = time.perf_counter() - t0
    log.info(f"  DONE in {elapsed:.0f}s  cost=${result.metadata['cost']['total_usd']:.4f}  file={result.file_path}")
    return Path(result.file_path)


def main() -> int:
    segment_paths: list[Path] = []
    total_cost = 0.0
    t_total = time.perf_counter()

    for slot, name in enumerate(SEGMENT_ORDER, start=1):
        if name is None:
            log.info(f"Slot {slot}: reusing pre-built segment 4 -> {SEGMENT_4_PREBUILT}")
            segment_paths.append(SEGMENT_4_PREBUILT)
            continue
        try:
            path = run_segment(name)
            segment_paths.append(path)
        except Exception as exc:
            log.exception(f"Segment '{name}' failed: {exc}")
            log.error("Continuing with remaining segments; failed segment will be skipped from final assembly.")

    log.info("")
    log.info(f"All segments done in {(time.perf_counter()-t_total):.0f}s")
    log.info(f"Segment files ({len(segment_paths)}):")
    for p in segment_paths:
        log.info(f"  {p}")

    # Final assembly: concat every produced segment into one lesson video.
    log.info("Final assembly: concatenating all segments...")
    combine = VideoCombine()
    final = combine.process(CapabilityInput(
        file_path=segment_paths[0],
        params={"clip_paths": [str(p) for p in segment_paths[1:]]},
    ))
    # Move to a stable named output
    final_path = output_path(".mp4", "selection_criterion_lesson")
    shutil.copyfile(final.file_path, final_path)
    Path(final.file_path).unlink(missing_ok=True)
    log.info(f"")
    log.info(f"FINAL LESSON VIDEO: {final_path}")
    log.info(f"  size: {final_path.stat().st_size:,} bytes")
    log.info(f"  mode: {final.metadata['mode']}")
    # Duration probe
    import subprocess, re
    probe = subprocess.run(["ffmpeg", "-i", str(final_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    m = re.search(r"Duration: (\d+:\d+:\d+\.\d+)", probe.stderr.decode('utf-8', errors='replace'))
    log.info(f"  duration: {m.group(1) if m else '?'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
