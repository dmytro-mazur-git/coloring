"""Clean up found coloring pages into printable line art (black ink on white, sized
for A4 at 300 DPI).

cleanup:
    crop to content -> crop inside a page frame (drops site captions on it) -> scale to
    print size -> ink = dark pixels + edges of gray fills -> finish.

finish:
    drop specks -> big solid black fills (much thicker than the drawing's own lines)
    become outlines -> too-thin lines are thickened (thick lines keep the artist's
    strokes) -> close small gaps -> drop specks again.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .imaging import (
    closed_regions,
    crop_to_content,
    disk,
    fit_scale,
    load_rgb,
    remove_small_components,
    save_ink,
    stroke_width,
    to_gray,
)

FRAME_LINE_FRAC = 0.45        # cleanup: a row/column this full of ink is a frame line
FRAME_EDGE_ZONE = 0.2         # ...when it lies within this share of the image from an edge
DARK_THRESHOLD = 110          # cleanup: gray below this is always ink
LIGHT_LINE_MAX_THRESHOLD = 200  # cleanup: upper bound of the adaptive ink threshold
FILL_WIDTH_FACTOR = 3         # ink thicker than this × max line width is a solid fill


def to_lineart(image: Path, out: Path, profile: dict) -> dict:
    """Write the cleaned-up line-art PNG to `out` and return metrics of the result."""
    ink = _finish(_cleanup(load_rgb(image)), profile)
    if not ink.any():
        raise ValueError("no line art left after processing")
    save_ink(ink, out)

    min_area = profile["min_component_area_px"]
    return {
        "path": str(out),
        "width": int(ink.shape[1]),
        "height": int(ink.shape[0]),
        "orientation": "landscape" if ink.shape[1] > ink.shape[0] else "portrait",
        "line_width_px": round(stroke_width(ink), 1),
        "closed_regions": closed_regions(ink, min_area),
        "ink_ratio": round(float(ink.mean()), 3),
    }


def _scale_to_print(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    s = fit_scale(w, h)
    interp = cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA
    return cv2.resize(img, (round(w * s), round(h * s)), interpolation=interp)


def _crop_box(mask: np.ndarray, pad_frac: float = 0.02) -> tuple[slice, slice]:
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return slice(None), slice(None)
    h, w = mask.shape
    pad = round(max(h, w) * pad_frac)
    return (slice(max(0, ys.min() - pad), min(h, ys.max() + pad + 1)),
            slice(max(0, xs.min() - pad), min(w, xs.max() + pad + 1)))


def _remove_frame(gray: np.ndarray) -> np.ndarray:
    """Crop inside a page frame: long straight ink lines near the edges (full or partial
    frames). Site captions/watermarks sitting on or outside the frame go with it."""
    ink = gray < 128
    h, w = ink.shape
    rows = np.flatnonzero(ink.mean(axis=1) > FRAME_LINE_FRAC)
    cols = np.flatnonzero(ink.mean(axis=0) > FRAME_LINE_FRAC)
    top = rows[rows < h * FRAME_EDGE_ZONE]
    bottom = rows[rows > h * (1 - FRAME_EDGE_ZONE)]
    left = cols[cols < w * FRAME_EDGE_ZONE]
    right = cols[cols > w * (1 - FRAME_EDGE_ZONE)]
    pad = round(max(h, w) * 0.025)   # captions often stick out above the frame line
    y0 = top.max() + pad if top.size else 0
    y1 = bottom.min() - pad if bottom.size else h
    x0 = left.max() + pad if left.size else 0
    x1 = right.min() - pad if right.size else w
    if y1 - y0 < h * 0.5 or x1 - x0 < w * 0.5:
        return gray
    return gray[y0:y1, x0:x1]


def _cleanup(rgb: np.ndarray) -> np.ndarray:
    gray = to_gray(rgb)
    gray = gray[_crop_box(gray < 200)]
    gray = _remove_frame(gray)
    gray = gray[_crop_box(gray < 200)]
    gray = _scale_to_print(gray)

    # Light "pencil" line art needs a higher threshold than bold ink: take Otsu's,
    # but never so low that faint lines break, nor so high that paper texture counts.
    otsu, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark = gray < float(np.clip(otsu, DARK_THRESHOLD, LIGHT_LINE_MAX_THRESHOLD))
    # Gray fills/shading become paper; their outlines are kept as thin edges.
    # Edges right next to dark lines are skipped so they do not thicken them.
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150) > 0
    near_dark = cv2.dilate(dark.astype(np.uint8), disk(7)) > 0
    return dark | (edges & ~near_dark)


def _finish(ink: np.ndarray, profile: dict) -> np.ndarray:
    min_area = profile["min_component_area_px"]
    lo, hi = profile["line_px"]
    target = (lo + hi) / 2

    ink = remove_small_components(ink, min_area)
    ink = _outline_fills(ink, hi, target)
    width = stroke_width(ink)
    # Found line art keeps the artist's strokes (tapering, solid eyes and brows):
    # too-thin lines are thickened, which keeps shapes; thick lines stay as drawn.
    if 0 < width < lo:
        ink = cv2.dilate(ink.astype(np.uint8), disk(target - width + 1)) > 0

    ink = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_CLOSE, disk(max(3, target * 0.6))) > 0
    ink = remove_small_components(ink, min_area)
    return crop_to_content(ink)


def _typical_line_width(ink: np.ndarray) -> float:
    """Width of the drawing's own lines: median distance-transform value on the ridge.
    Ridges of solid areas are short compared to their area, so lines dominate."""
    dist = cv2.distanceTransform(ink.astype(np.uint8), cv2.DIST_L2, 5)
    ridge = (dist > 0) & (dist >= cv2.dilate(dist, np.ones((3, 3), np.uint8)))
    values = dist[ridge]
    return float(2 * np.median(values)) if values.size else 0.0


def _outline_fills(ink: np.ndarray, max_line: float, target: float) -> np.ndarray:
    """Replace solid areas much thicker than a line with their outline; small
    solid details (pupils, dots) stay black.

    "Much thicker" is relative to both the profile and the drawing's own lines, so
    bold-outline line art is not hollowed into double contours."""
    line = max(max_line, _typical_line_width(ink))
    fills = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_OPEN, disk(FILL_WIDTH_FACTOR * line)) > 0
    if not fills.any():
        return ink
    inner = cv2.erode(fills.astype(np.uint8), disk(2 * target)) > 0
    return ink & ~inner
