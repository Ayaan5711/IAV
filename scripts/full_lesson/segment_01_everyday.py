"""Segment 1: Selection in everyday life (0:00-1:00). ~40s."""
from iav.capabilities.video_hybrid_segment import SegmentPlan
from scripts.full_lesson._shared import veo, infog

PLAN = SegmentPlan(
    title="Seg 1: Selection in everyday life",
    beats=[
        veo(8, "A woman in her thirties stands in a grocery store aisle holding two "
               "different boxes of cookies, one in each hand, comparing them thoughtfully. "
               "Bright warm indoor lighting."),
        veo(8, "The same woman smiles, places one box into her shopping cart, and "
               "pushes the cart down the aisle. Same lighting, same wardrobe.",
            chain=True),
        veo(8, "Different scene: a man in his thirties at a modern car dealership "
               "looking between two different cars (one silver sedan, one blue "
               "compact SUV) parked side by side. Soft natural lighting through "
               "large windows."),
        infog(10,
              "Title in bold dark navy sans-serif at the top center: 'EVERY DAY, WE "
              "CHOOSE'. Below the title, three equally-sized card icons in a row, "
              "each with a simple flat illustration: left card shows a shopping "
              "basket with cookies, middle card shows a car silhouette, right card "
              "shows a signpost at a fork in a path. Each card has a short "
              "slate-gray caption underneath: 'What to buy', 'What to drive', "
              "'Which way to go'.",
              "Animate: the three cards fade in one after another from left to "
              "right (shopping basket first, then car, then signpost), each "
              "landing with a gentle bounce. The title stays stable throughout."),
    ],
    narration_script=(
        "Every day, we make choices. Which box of cookies to buy. Which car fits "
        "the family. Which direction to take in life. These look like very "
        "different decisions. But they share the same shape: we have options, and "
        "we have reasons to prefer one over the others. That is what selection "
        "is -- not just picking, but picking for a reason."
    ),
)
