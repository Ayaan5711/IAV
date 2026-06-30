"""Local file I/O for the POC. Swap with cloud storage post-POC."""

from iav.storage.local import (
    inputs_dir,
    output_path,
    outputs_dir,
    save_input,
    save_output,
)

__all__ = ["inputs_dir", "output_path", "outputs_dir", "save_input", "save_output"]
