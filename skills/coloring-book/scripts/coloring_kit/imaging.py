"""Shared image helpers: loading, print geometry, ink masks and stroke/region measurements."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import imagehash
from PIL import Image, ImageFilter, ImageOps

A4_MM = (210.0, 297.0)
MM_PER_INCH = 25.4


def printable_px(dpi: int = 300, margin_mm: float = 10.0) -> tuple[int, int]:
    """Printable area of a portrait A4 page in pixels (≈2244×3272 at 300 DPI, 10 mm)."""
    w = round((A4_MM[0] - 2 * margin_mm) / MM_PER_INCH * dpi)
    h = round((A4_MM[1] - 2 * margin_mm) / MM_PER_INCH * dpi)
    return w, h


def fit_scale(w: int, h: int, box: tuple[int, int] | None = None) -> float:
    """Scale that fits a w×h image into the printable box in its better orientation."""
    bw, bh = box or printable_px()
    if w > h:
        bw, bh = bh, bw
    return min(bw / w, bh / h)


def load_rgb(path: Path) -> np.ndarray:
    """RGB uint8 array; EXIF orientation applied, transparency composited onto white."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            im = Image.alpha_composite(bg, im)
        return np.asarray(im.convert("RGB")).copy()


def to_gray(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def resize_long(img: np.ndarray, long_side: int) -> np.ndarray:
    h, w = img.shape[:2]
    s = long_side / max(h, w)
    if abs(s - 1) < 1e-3:
        return img
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC
    return cv2.resize(img, (round(w * s), round(h * s)), interpolation=interp)


def border_strip(img: np.ndarray, frac: float = 0.03) -> np.ndarray:
    """Pixels of a frame along the image edges (flattened to N×C or N)."""
    h, w = img.shape[:2]
    t = max(1, round(min(h, w) * frac))
    parts = [img[:t], img[-t:], img[t:-t, :t], img[t:-t, -t:]]
    if img.ndim == 3:
        return np.concatenate([p.reshape(-1, img.shape[2]) for p in parts])
    return np.concatenate([p.reshape(-1) for p in parts])


def disk(diameter: int) -> np.ndarray:
    d = max(1, int(round(diameter)))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (d, d))


def stroke_width(ink: np.ndarray) -> float:
    """Average stroke width of a boolean ink mask: 2·area / perimeter (exact for long strokes)."""
    mask = ink.astype(np.uint8)
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    perimeter = sum(cv2.arcLength(c, True) for c in contours)
    return float(2 * mask.sum() / perimeter) if perimeter else 0.0


def remove_small_components(ink: np.ndarray, min_area: int) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return keep[labels]


def closed_regions(ink: np.ndarray, min_area: int) -> int:
    """Number of colorable areas: white components not touching the image border."""
    paper = (~ink).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(paper, connectivity=4)
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    big = stats[:, cv2.CC_STAT_AREA] >= min_area
    big[0] = False
    big[border] = False
    return int(big.sum())


def crop_to_content(ink: np.ndarray, pad_frac: float = 0.02) -> np.ndarray:
    ys, xs = np.nonzero(ink)
    if ys.size == 0:
        return ink
    h, w = ink.shape
    pad = round(max(h, w) * pad_frac)
    y0, y1 = max(0, ys.min() - pad), min(h, ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(w, xs.max() + pad + 1)
    return ink[y0:y1, x0:x1]


def save_ink(ink: np.ndarray, out: Path) -> None:
    """Black ink on white paper, 8-bit grayscale PNG."""
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.where(ink, 0, 255).astype(np.uint8), mode="L").save(out, optimize=True)


def perceptual_hash(im: Image.Image) -> str:
    """pHash of a slightly blurred copy: thin line art otherwise hashes unstably.
    Resized/recompressed/cropped copies land within ~6 bits, different pictures ≥ ~20."""
    gray = im.convert("L").resize((256, 256), Image.LANCZOS).filter(ImageFilter.GaussianBlur(2))
    return str(imagehash.phash(gray))
