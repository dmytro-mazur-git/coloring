"""Turn images into clean printable line art (black ink on white, sized for A4 at 300 DPI).

cleanup (stage 1 and 3 outputs, already line art):
    crop to content -> crop inside a page frame (drops site captions on it) -> scale to print size -> ink = dark pixels + edges of gray fills
    -> finish.

convert (stage 2, regular images):
    resize -> bilateral denoise -> white-out a uniform background -> k-means color
    quantization in Lab -> mode filter -> boundaries between color regions
    (+ Canny detail edges for medium/hard) -> crop -> scale to print size -> finish.

finish (both):
    drop specks -> big solid black fills (much thicker than the drawing's own lines)
    become outlines -> stroke width: cleanup only thickens too-thin lines (keeps the
    artist's strokes); convert redraws off-profile lines from the skeleton at the
    profile's target width -> close small gaps -> drop specks again.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from skimage.morphology import skeletonize

from .imaging import (
    border_strip,
    closed_regions,
    crop_to_content,
    disk,
    fit_scale,
    load_rgb,
    remove_small_components,
    resize_long,
    save_ink,
    stroke_width,
    to_gray,
)

Mode = Literal["cleanup", "convert"]

CONVERT_WORK_LONG_SIDE = 1200
FRAME_LINE_FRAC = 0.45        # cleanup: a row/column this full of ink is a frame line
FRAME_EDGE_ZONE = 0.2         # ...when it lies within this share of the image from an edge
DARK_THRESHOLD = 110          # cleanup: gray below this is always ink
LIGHT_LINE_MAX_THRESHOLD = 200  # cleanup: upper bound of the adaptive ink threshold
BG_UNIFORM_MAX_DIST = 18.0    # mean Lab distance of the border to call the background uniform
BG_MATCH_DIST = 12.0          # Lab distance of a pixel to the background color
BG_LABEL = 255                # label reserved for the background region
PARALLEL_MERGE_PX = 5         # convert: lines closer than this (work px) merge into one
DARK_LAB_L = 70               # OpenCV Lab L (0..255) below which a color cluster is ink
FILL_WIDTH_FACTOR = 3         # ink thicker than this × max line width is a solid fill


def to_lineart(image: Path, out: Path, mode: Mode, profile: dict) -> dict:
    """Write the line-art PNG to `out` and return metrics of the result."""
    rgb = load_rgb(image)
    if mode == "cleanup":
        ink = _cleanup(rgb)
    elif mode == "convert":
        ink = _convert(rgb, profile)
    else:
        raise ValueError(f"unknown mode: {mode}")

    ink = _finish(ink, profile, mode)
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


def _convert(rgb: np.ndarray, profile: dict) -> np.ndarray:
    work = resize_long(rgb, CONVERT_WORK_LONG_SIDE)
    smooth = cv2.bilateralFilter(work, 9, 60, 60)
    smooth = cv2.bilateralFilter(smooth, 9, 60, 60)

    lab = cv2.cvtColor(smooth, cv2.COLOR_RGB2LAB).astype(np.float32)
    background = _background_mask(lab)

    labels, centers = _quantize(lab, profile.get("kmeans_k", 10))
    if background is not None:
        # The background is its own region, so the subject's silhouette is always
        # outlined, even where the subject's color is close to the background's.
        labels[background] = BG_LABEL
    labels = cv2.medianBlur(labels, 7)
    labels = cv2.medianBlur(labels, 5)

    # Near-black clusters are the drawing's own outlines (cartoons) or solid black
    # parts: they are ink as they are. Boundaries are taken only between lighter
    # regions, otherwise every black outline would turn into a double line.
    dark = np.isin(labels, np.flatnonzero(centers[:, 0] < DARK_LAB_L))
    edges = np.zeros(labels.shape, dtype=bool)
    edges[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    edges[1:, :] |= labels[1:, :] != labels[:-1, :]
    edges &= ~(cv2.dilate(dark.astype(np.uint8), disk(5)) > 0)
    edges |= dark

    if profile.get("detail_edges", False):
        gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
        detail = cv2.Canny(gray, 60, 160) > 0
        if background is not None:
            detail &= ~background
        edges |= detail & ~(cv2.dilate(dark.astype(np.uint8), disk(5)) > 0)

    # Region boundaries and Canny edges often run as near-parallel pairs a few pixels
    # apart: merge them so _finish redraws a single line from the skeleton.
    edges = cv2.morphologyEx(edges.astype(np.uint8), cv2.MORPH_CLOSE, disk(PARALLEL_MERGE_PX)) > 0

    subject = edges if background is None else (edges | ~background)
    edges = edges[_crop_box(subject)]

    # Upscale the 1-px edges smoothly; _finish thickens them to the profile.
    scaled = _scale_to_print(edges.astype(np.float32))
    return scaled > 0.25


def _background_mask(lab: np.ndarray) -> np.ndarray | None:
    """Mask of a uniform background connected to the image border, or None."""
    border = border_strip(lab)
    bg = np.median(border, axis=0)
    if float(np.linalg.norm(border - bg, axis=1).mean()) > BG_UNIFORM_MAX_DIST:
        return None
    dist = np.linalg.norm(lab - bg, axis=2)
    near = dist < BG_MATCH_DIST
    # Faint edges of the color distance stop the flood fill where the subject's color
    # is close to the background's (cream body on off-white paper).
    amplified = np.clip(dist * 10, 0, 255).astype(np.uint8)
    barrier = cv2.Canny(amplified, 30, 90) > 0
    near = (near & ~(cv2.dilate(barrier.astype(np.uint8), disk(3)) > 0)).astype(np.uint8)
    _, comp = cv2.connectedComponents(near, connectivity=4)
    on_border = np.unique(np.concatenate([comp[0], comp[-1], comp[:, 0], comp[:, -1]]))
    on_border = on_border[on_border > 0]
    return np.isin(comp, on_border)


def _quantize(lab: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """k-means color labels (uint8) and Lab centers. Centers are fitted on a pixel sample."""
    pixels = lab.reshape(-1, 3)
    rng = np.random.default_rng(0)
    sample = pixels[rng.choice(len(pixels), size=min(len(pixels), 60_000), replace=False)]
    k = int(min(k, len(np.unique(sample.round(), axis=0))))
    if k < 2:
        return np.zeros(lab.shape[:2], dtype=np.uint8), pixels.mean(axis=0, keepdims=True)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    cv2.setRNGSeed(0)
    _, _, centers = cv2.kmeans(sample, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    best = np.full(len(pixels), np.inf, dtype=np.float32)
    labels = np.zeros(len(pixels), dtype=np.uint8)
    for i, center in enumerate(centers):
        d = ((pixels - center) ** 2).sum(axis=1)
        closer = d < best
        best[closer] = d[closer]
        labels[closer] = i
    return labels.reshape(lab.shape[:2]), centers


def _finish(ink: np.ndarray, profile: dict, mode: Mode) -> np.ndarray:
    min_area = profile["min_component_area_px"]
    lo, hi = profile["line_px"]
    target = (lo + hi) / 2

    ink = remove_small_components(ink, min_area)
    ink = _outline_fills(ink, hi, target)
    width = stroke_width(ink)
    if mode == "cleanup":
        # Found line art keeps the artist's strokes (tapering, solid eyes and brows):
        # too-thin lines are thickened, which keeps shapes; thick lines stay as drawn.
        if 0 < width < lo:
            ink = cv2.dilate(ink.astype(np.uint8), disk(target - width + 1)) > 0
    elif width and not lo <= width <= hi:
        # Converted edges are our own lines: redraw them uniformly from the skeleton.
        # Smooth jagged edges first: they turn into spurs on the skeleton.
        smooth = cv2.GaussianBlur(ink.astype(np.float32), (0, 0), max(1.0, width / 4)) > 0.5
        skeleton = _prune_spurs(skeletonize(smooth), max_len=round(width + 2 * target))
        ink = cv2.dilate(skeleton.astype(np.uint8), disk(target)) > 0

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


_NEIGHBORS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _prune_spurs(skeleton: np.ndarray, max_len: int) -> np.ndarray:
    """Remove short side branches: paths from an endpoint that reach a junction
    within `max_len` pixels. Free-standing short strokes are kept."""
    skel = skeleton.astype(np.uint8)
    counts = cv2.filter2D(skel, -1, np.ones((3, 3), np.float32), borderType=cv2.BORDER_CONSTANT) - skel
    endpoints = np.argwhere((skel == 1) & (counts == 1))
    h, w = skel.shape
    for y, x in endpoints:
        path, prev = [(y, x)], None
        cy, cx = y, x
        while len(path) <= max_len:
            nxt = [(cy + dy, cx + dx) for dy, dx in _NEIGHBORS
                   if 0 <= cy + dy < h and 0 <= cx + dx < w and skel[cy + dy, cx + dx]
                   and (cy + dy, cx + dx) != prev and (cy + dy, cx + dx) not in path]
            if len(nxt) != 1:
                break
            prev = (cy, cx)
            cy, cx = nxt[0]
            if counts[cy, cx] >= 3:      # reached a junction: this was a spur
                for py, px in path:
                    skel[py, px] = 0
                break
            path.append((cy, cx))
    return skel.astype(bool)
