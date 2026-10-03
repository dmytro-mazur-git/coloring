"""Cheap pixel metrics used to filter candidates before any vision-LLM look.

All scores are heuristics in 0..1; they rank and pre-filter candidates, the final
judgement is made by a subagent looking at the thumbnail.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .imaging import (
    border_strip,
    closed_regions,
    fit_scale,
    load_rgb,
    perceptual_hash,
    resize_long,
    stroke_width,
    to_gray,
)
from .models import ImageMetrics

WORK_LONG_SIDE = 1024
# Tolerance around the profile ranges: cleanup normalizes strokes, so only gross misfits matter.
LINE_TOLERANCE = (0.5, 2.0)
REGION_TOLERANCE = (0.5, 1.5)
# Ink farther than this from paper (share of the long side) belongs to a solid fill, not a line.
SOLID_DT_FRAC = 6 / 1024


def _ramp(x: float, lo: float, hi: float) -> float:
    """0 at lo, 1 at hi (works for lo > hi too), clipped."""
    return float(np.clip((x - lo) / (hi - lo), 0.0, 1.0))


def _in_band(x: float, lo: float, hi: float, soft: float) -> float:
    """1 inside [lo, hi], fading to 0 at `soft` relative distance outside."""
    if lo <= x <= hi:
        return 1.0
    edge = lo if x < lo else hi
    return float(max(0.0, 1 - abs(x - edge) / (edge * soft)))


def _lineart_score(gray: np.ndarray, color_ratio: float, gray_ratio: float, ink_ratio: float,
                   solid_ratio: float) -> float:
    bimodal = float(((gray < 80) | (gray > 200)).mean())
    white_border = float((border_strip(gray) > 200).mean())
    ink_ok = _in_band(ink_ratio, 0.02, 0.35, soft=1.0)
    base = 0.45 * bimodal + 0.3 * white_border + 0.25 * ink_ok
    # Color, gray shading and big solid black areas (silhouettes, filled spots)
    # are what disqualify an image as a coloring page.
    colorless = _ramp(color_ratio, 0.10, 0.0)
    shading = _ramp(gray_ratio, 0.15, 0.5)
    solid = _ramp(solid_ratio, 0.10, 0.40)
    return base * (0.3 + 0.7 * colorless) * (1 - 0.5 * shading) * (1 - 0.8 * solid)


def _convertibility_score(rgb: np.ndarray, gray: np.ndarray) -> float:
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    border = border_strip(lab)
    bg = np.median(border, axis=0)
    border_uniform = _ramp(float(np.linalg.norm(border - bg, axis=1).mean()), 30.0, 5.0)

    fg = np.linalg.norm(lab - bg, axis=2) > 25
    fill = float(fg.mean())
    subject_fill = _in_band(fill, 0.15, 0.75, soft=1.0)
    contrast = _ramp(float(np.abs(gray[fg].mean() - gray[~fg].mean())) if 0 < fill < 1 else 0.0, 10, 80)

    # Flat colors (cartoon, clipart) convert cleanly; photos have hundreds of shades.
    q = (rgb // 16).reshape(-1, 3)
    codes = q[:, 0].astype(np.int32) * 256 + q[:, 1].astype(np.int32) * 16 + q[:, 2]
    counts = np.sort(np.bincount(codes, minlength=4096))[::-1]
    n90 = int(np.searchsorted(np.cumsum(counts), 0.9 * codes.size) + 1)
    flatness = _ramp(n90, 250, 20)

    return 0.3 * border_uniform + 0.2 * subject_fill + 0.2 * contrast + 0.3 * flatness


def _text_likelihood(ink: np.ndarray) -> float:
    """Rows of small, similarly sized, closely spaced glyph-like blobs suggest text."""
    h, _ = ink.shape
    n, _, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    if n <= 1:
        return 0.0
    x, y, bw, bh = (stats[1:, i] for i in
                    (cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP, cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT))
    glyph = (bh > 0.006 * h) & (bh < 0.05 * h) & (bw < 1.5 * bh) & (bw > 0.15 * bh)
    if glyph.sum() < 4 or glyph.sum() > 2000:   # thousands of blobs = texture/noise, not text
        return 0.0
    boxes = sorted(zip(x[glyph], y[glyph] + bh[glyph], bw[glyph], bh[glyph]), key=lambda b: b[0])
    best = 1
    for i, (x0, base0, w0, h0) in enumerate(boxes):
        run, right, base = 1, x0 + w0, base0
        for x1, base1, w1, h1 in boxes[i + 1:]:
            if x1 - right > 1.2 * h0:
                break
            if abs(base1 - base) < 0.35 * h0 and 0.5 < h1 / h0 < 2.0:
                run, right = run + 1, x1 + w1
        best = max(best, run)
    return _ramp(best, 3, 10)


def analyze(image: Path, profile: dict) -> ImageMetrics:
    """Compute metrics for one image against a difficulty profile (see config.yaml)."""
    rgb_full = load_rgb(image)
    height, width = rgb_full.shape[:2]
    rgb = resize_long(rgb_full, WORK_LONG_SIDE)
    gray = to_gray(rgb)
    to_print = fit_scale(gray.shape[1], gray.shape[0])

    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    color_ratio = float(((hsv[..., 1] > 64) & (hsv[..., 2] > 50)).mean())
    gray_ratio = float(((gray >= 80) & (gray <= 200)).mean())

    otsu_t, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = gray < min(otsu_t, 128)   # gray shading is not ink
    ink_ratio = float(ink.mean())
    dist = cv2.distanceTransform(ink.astype(np.uint8), cv2.DIST_L2, 5)
    solid_ratio = float((dist > SOLID_DT_FRAC * WORK_LONG_SIDE).sum() / max(ink.sum(), 1))

    line_px = stroke_width(ink) * to_print
    min_area = max(4, round(profile["min_component_area_px"] / to_print**2))
    regions = closed_regions(ink, min_area)

    lo, hi = profile["line_px"]
    rlo, rhi = profile["regions"]
    fits = (lo * LINE_TOLERANCE[0] <= line_px <= hi * LINE_TOLERANCE[1]
            and rlo * REGION_TOLERANCE[0] <= regions <= max(rhi * REGION_TOLERANCE[1], 1))

    with Image.open(image) as im:
        phash = perceptual_hash(im)

    return ImageMetrics(
        width=width,
        height=height,
        lineart_score=round(_lineart_score(gray, color_ratio, gray_ratio, ink_ratio, solid_ratio), 3),
        convertibility_score=round(_convertibility_score(rgb, gray), 3),
        color_ratio=round(color_ratio, 3),
        gray_ratio=round(gray_ratio, 3),
        ink_ratio=round(ink_ratio, 3),
        solid_ratio=round(solid_ratio, 3),
        line_width_px=round(line_px, 1),
        closed_regions=regions,
        text_likelihood=round(_text_likelihood(ink), 3),
        phash=phash,
        fits_profile=bool(fits),
    )


def thumbnail(image: Path, max_px: int, out: Path | None = None) -> Path:
    """Small PNG copy for vision review.

    Default location: `<page dir>/thumbs/<name>.png` for files in `candidates/`,
    otherwise a `thumbs/` directory next to the image.
    """
    if out is None:
        base = image.parent.parent if image.parent.name == "candidates" else image.parent
        out = base / "thumbs" / f"{image.stem}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    im = Image.fromarray(load_rgb(image))   # transparency composited onto white
    im.thumbnail((max_px, max_px), Image.LANCZOS)
    im.save(out, optimize=True)
    return out
