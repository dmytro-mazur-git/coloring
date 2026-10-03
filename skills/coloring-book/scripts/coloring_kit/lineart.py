"""Turn images into clean printable line art.

cleanup (stage 1 and 3 outputs, already line art):
    grayscale -> Otsu/adaptive binarize -> drop gray fills -> remove components
    smaller than profile.min_component_area_px -> normalize stroke width to
    profile.line_px -> crop to content -> upscale to print size.

convert (stage 2, regular images):
    resize -> bilateral/median denoise -> optional background removal ->
    k-means color quantization (k=6..12) -> boundaries between color regions
    OR Canny on the smoothed image -> morphological close (seal gaps) ->
    thicken to profile.line_px -> remove small components -> black on white.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

Mode = Literal["cleanup", "convert"]


def to_lineart(image: Path, out: Path, mode: Mode, profile: dict) -> dict:
    """Write a 1-bit-looking PNG to `out`; return metrics of the result."""
    raise NotImplementedError
