"""Turn images into clean printable line art (black ink on white, sized for A4 at 300 DPI).

cleanup (stage 1 and 3 outputs, already line art):
    crop to content -> scale to print size -> ink = dark pixels + edges of gray fills
    -> finish.

convert (stage 2, regular images):
    resize -> bilateral denoise -> white-out a uniform background -> k-means color
    quantization in Lab -> mode filter -> boundaries between color regions
    (+ Canny detail edges for medium/hard) -> crop -> scale to print size -> finish.

finish (both):
    drop specks -> if stroke width is off-profile: skeletonize and redraw at the
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
DARK_THRESHOLD = 110          # gray below this is ink in cleanup mode
BG_UNIFORM_MAX_DIST = 18.0    # mean Lab distance of the border to call the background uniform
BG_MATCH_DIST = 22.0          # Lab distance of a pixel to the background color to whiten it


def to_lineart(image: Path, out: Path, mode: Mode, profile: dict) -> dict:
    """Write the line-art PNG to `out` and return metrics of the result."""
    rgb = load_rgb(image)
    if mode == "cleanup":
        ink = _cleanup(rgb)
    elif mode == "convert":
        ink = _convert(rgb, profile)
    else:
        raise ValueError(f"unknown mode: {mode}")

    ink = _finish(ink, profile)
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


def _cleanup(rgb: np.ndarray) -> np.ndarray:
    gray = to_gray(rgb)
    gray = gray[_crop_box(gray < 200)]
    gray = _scale_to_print(gray)

    dark = gray < DARK_THRESHOLD
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
    if background is not None:
        lab[background] = cv2.cvtColor(np.full((1, 1, 3), 255, np.uint8), cv2.COLOR_RGB2LAB)[0, 0]

    labels = _quantize(lab, profile.get("kmeans_k", 10))
    labels = cv2.medianBlur(labels, 7)
    labels = cv2.medianBlur(labels, 5)

    edges = np.zeros(labels.shape, dtype=bool)
    edges[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    edges[1:, :] |= labels[1:, :] != labels[:-1, :]

    if profile.get("detail_edges", False):
        gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
        detail = cv2.Canny(gray, 60, 160) > 0
        if background is not None:
            detail &= ~background
        edges |= detail

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
    near = (np.linalg.norm(lab - bg, axis=2) < BG_MATCH_DIST).astype(np.uint8)
    _, comp = cv2.connectedComponents(near, connectivity=4)
    on_border = np.unique(np.concatenate([comp[0], comp[-1], comp[:, 0], comp[:, -1]]))
    on_border = on_border[on_border > 0]
    return np.isin(comp, on_border)


def _quantize(lab: np.ndarray, k: int) -> np.ndarray:
    """k-means color labels (uint8). Centers are fitted on a pixel sample for speed."""
    pixels = lab.reshape(-1, 3)
    rng = np.random.default_rng(0)
    sample = pixels[rng.choice(len(pixels), size=min(len(pixels), 60_000), replace=False)]
    k = int(min(k, len(np.unique(sample.round(), axis=0))))
    if k < 2:
        return np.zeros(lab.shape[:2], dtype=np.uint8)
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
    return labels.reshape(lab.shape[:2])


def _finish(ink: np.ndarray, profile: dict) -> np.ndarray:
    min_area = profile["min_component_area_px"]
    lo, hi = profile["line_px"]
    target = (lo + hi) / 2

    ink = remove_small_components(ink, min_area)
    width = stroke_width(ink)
    if width and not lo * 0.8 <= width <= hi * 1.2:
        # Smooth jagged edges first: they turn into spurs on the skeleton.
        smooth = cv2.GaussianBlur(ink.astype(np.float32), (0, 0), max(1.0, width / 4)) > 0.5
        skeleton = _prune_spurs(skeletonize(smooth), max_len=round(width + 2 * target))
        ink = cv2.dilate(skeleton.astype(np.uint8), disk(target)) > 0

    ink = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_CLOSE, disk(max(3, target * 0.6))) > 0
    ink = remove_small_components(ink, min_area)
    return crop_to_content(ink)


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
