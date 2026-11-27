"""Phase 3: run the full Selection Criterion lesson under T1d pattern.

Runs all 11 segment plans sequentially at one target resolution,
assembles the final lesson MP4 from the segment outputs. By default
runs 720p; pass --resolution 1080p for the hi-res pass.

Usage:
  python scripts/full_lesson/t1d_full_lesson.py                 # 720p
  python scripts/full_lesson/t1d_full_lesson.py --resolution 1080p

Both resolutions share the same plans and the same logic; only Omni's
realistic beats cost more at 1080p ($0.15/s vs $0.07/s). Nano Banana
Pro slides are generated at the right pixel size for the target.
"""
import argparse
import logging
import shutil
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            "/tmp/claude-0/-home-user-IAV/e9b40bb4-f11e-517f-8664-695af61234e2/scratchpad/t1d_full_lesson.log"
        ),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("t1d-full")

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.full_lesson.t1d_runner import run_segment
from iav.capabilities.video_combine import VideoCombine
from iav.capabilities.base import CapabilityInput
from iav.storage import output_path


SEGMENT_MODULES = [
    "scripts.full_lesson.t1d_plans.seg01",
    "scripts.full_lesson.t1d_plans.seg02",
    "scripts.full_lesson.t1d_plans.seg03",
    "scripts.full_lesson.t1d_plans.seg04",
    "scripts.full_lesson.t1d_plans.seg05",
    "scripts.full_lesson.t1d_plans.seg06",
    "scripts.full_lesson.t1d_plans.seg07",
    "scripts.full_lesson.t1d_plans.seg08",
    "scripts.full_lesson.t1d_plans.seg09",
    "scripts.full_lesson.t1d_plans.seg10",
    "scripts.full_lesson.t1d_plans.seg11",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resolution", default="720p", choices=["720p", "1080p"])
    args = ap.parse_args()
    resolution = args.resolution

    import importlib
    t_total = time.perf_counter()
    segment_paths: list[Path] = []
    results: list[dict] = []

    for mod_name in SEGMENT_MODULES:
        plan = importlib.import_module(mod_name).PLAN
        log.info("=" * 60)
        log.info("Segment %s @ %s  (%d sub-shots)", plan.output_name, resolution,
                 len(plan.sub_shots))
        log.info("=" * 60)
        t0 = time.perf_counter()
        try:
            final = run_segment(plan, resolution=resolution)
            elapsed = time.perf_counter() - t0
            segment_paths.append(final)
            results.append({"name": plan.output_name, "path": final,
                           "wall_seconds": elapsed, "status": "ok"})
            log.info("[%s @ %s] OK in %.1fs", plan.output_name, resolution, elapsed)
        except Exception as exc:
            log.exception("Segment %s failed: %s", plan.output_name, exc)
            results.append({"name": plan.output_name, "status": "failed", "error": str(exc)})

    if not segment_paths:
        log.error("All segments failed, aborting final assembly")
        return 1

    log.info("=" * 60)
    log.info("Final assembly: concatenating %d segments ...", len(segment_paths))
    log.info("=" * 60)

    from iav.models.config import load_config
    combine = VideoCombine(config=load_config())
    combined = combine.process(CapabilityInput(
        file_path=segment_paths[0],
        params={"clip_paths": [str(p) for p in segment_paths[1:]]},
    ))

    final_lesson = output_path(".mp4", f"t1d_lesson_{resolution}")
    shutil.copyfile(combined.file_path, final_lesson)
    Path(combined.file_path).unlink(missing_ok=True)

    import subprocess, re
    probe = subprocess.run(["ffmpeg", "-i", str(final_lesson)],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    m = re.search(r"Duration: (\d+:\d+:\d+\.\d+)",
                  probe.stderr.decode(errors="replace"))

    log.info("")
    log.info("=== FULL LESSON (%s) DONE ===", resolution)
    log.info("File: %s", final_lesson)
    log.info("Size: %d bytes", final_lesson.stat().st_size)
    log.info("Duration: %s", m.group(1) if m else "?")
    log.info("End-to-end wall-clock: %.1fs", time.perf_counter() - t_total)
    log.info("")
    log.info("Per-segment results:")
    for r in results:
        if r["status"] == "ok":
            log.info("  %-15s %4ds  %s", r["name"], int(r["wall_seconds"]), r["path"])
        else:
            log.info("  %-15s FAILED: %s", r["name"], r.get("error", ""))

    return 0


if __name__ == "__main__":
    sys.exit(main())
