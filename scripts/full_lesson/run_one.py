"""Run a single segment plan end-to-end. Usage:

    python3 scripts/full_lesson/run_one.py segment_04_essential_desirable
"""
import importlib
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from iav.capabilities.video_hybrid_segment import VideoHybridSegment
from iav.capabilities.base import CapabilityInput


def main(mod_name: str) -> int:
    mod = importlib.import_module(f"scripts.full_lesson.{mod_name}")
    plan = mod.PLAN
    print(f"Running: {plan.title}")
    print(f"Beats:   {len(plan.beats)} ({'/'.join(b.kind for b in plan.beats)})")
    t0 = time.perf_counter()
    cap = VideoHybridSegment()
    result = cap.process(CapabilityInput(params={"plan": plan}))
    elapsed = time.perf_counter() - t0
    print("")
    print(f"DONE in {elapsed:.0f}s")
    print(f"Output: {result.file_path}")
    print(f"Size:   {result.metadata['output_bytes']:,} bytes")
    print(f"Cost:   ${result.metadata['cost']['total_usd']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "segment_04_essential_desirable"))
