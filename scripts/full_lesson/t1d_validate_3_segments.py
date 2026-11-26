"""Phase 1 validation: run T1d pattern on segments 2, 7, 11 at 720p.

Produces three segment MP4s + a plain-text comparison summary. If all
three feel right, we promote the T1d pattern into video_hybrid_segment.py
and generate the full lesson at 720p and 1080p.
"""
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            "/tmp/claude-0/-home-user-IAV/e9b40bb4-f11e-517f-8664-695af61234e2/scratchpad/t1d_phase1_progress.log"
        ),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("t1d-phase1")

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.full_lesson.t1d_runner import run_segment
from scripts.full_lesson.t1d_plans.seg02 import PLAN as SEG02_PLAN
from scripts.full_lesson.t1d_plans.seg07 import PLAN as SEG07_PLAN
from scripts.full_lesson.t1d_plans.seg11 import PLAN as SEG11_PLAN


SEGMENTS = [SEG02_PLAN, SEG07_PLAN, SEG11_PLAN]


def main() -> int:
    t_total = time.perf_counter()
    results: list[dict] = []

    for plan in SEGMENTS:
        log.info("=" * 60)
        log.info("Running %s (%d sub-shots)", plan.output_name, len(plan.sub_shots))
        log.info("=" * 60)
        t0 = time.perf_counter()
        try:
            final = run_segment(plan, resolution="720p")
            elapsed = time.perf_counter() - t0
            results.append({
                "name": plan.output_name,
                "path": final,
                "subshots": len(plan.sub_shots),
                "wall_seconds": elapsed,
                "status": "ok",
            })
            log.info("  %s OK in %.1fs -> %s", plan.output_name, elapsed, final)
        except Exception as exc:
            log.exception("Segment %s failed: %s", plan.output_name, exc)
            results.append({
                "name": plan.output_name,
                "error": str(exc),
                "status": "failed",
            })

    log.info("=" * 60)
    log.info("Phase 1 complete in %.1fs", time.perf_counter() - t_total)
    log.info("=" * 60)
    for r in results:
        if r["status"] == "ok":
            log.info("  %-15s %4ds  %2d sub-shots  %s", r["name"], int(r["wall_seconds"]),
                     r["subshots"], r["path"])
        else:
            log.info("  %-15s FAILED: %s", r["name"], r["error"])

    return 0 if all(r["status"] == "ok" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
