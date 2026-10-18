import cv2
import numpy as np
import pytest
from PIL import Image

from coloring_kit.imaging import printable_px
from coloring_kit.lineart import to_lineart


def _pixels(path):
    with Image.open(path) as im:
        return np.asarray(im.convert("L"))


@pytest.mark.parametrize("profile", ["easy", "medium", "hard"])
@pytest.mark.parametrize("name,mode", [("coloring.png", "cleanup"), ("clipart.png", "convert")])
def test_output_is_binary_print_sized_and_fits_profile(images, cfg, tmp_path, name, mode, profile):
    p = cfg["profiles"][profile]
    out = tmp_path / f"{profile}.png"
    result = to_lineart(images / name, out, mode, p)

    px = _pixels(out)
    assert set(np.unique(px)) <= {0, 255}

    pw, ph = printable_px()
    long_box, short_box = max(pw, ph), min(pw, ph)
    assert max(px.shape) <= long_box and min(px.shape) <= short_box
    assert max(px.shape) >= 0.8 * long_box or min(px.shape) >= 0.8 * short_box

    lo, hi = p["line_px"]
    if mode == "convert":
        assert lo * 0.8 <= result["line_width_px"] <= hi * 1.2
    else:
        # cleanup keeps the artist's line weight, only thickening too-thin lines
        assert result["line_width_px"] >= lo * 0.8
    assert result["closed_regions"] >= 4


def test_cleanup_removes_gray_fill(images, cfg, tmp_path):
    out = tmp_path / "c.png"
    to_lineart(images / "coloring.png", out, "cleanup", cfg["profiles"]["medium"])
    px = _pixels(out)
    h, w = px.shape
    # Center of the gray-filled ellipse (lower part of the page) must be paper now.
    assert px[int(h * 0.82), w // 2] == 255


def test_convert_finds_house_parts(images, cfg, tmp_path):
    result = to_lineart(images / "clipart.png", tmp_path / "h.png", "convert", cfg["profiles"]["easy"])
    # wall, roof, door, window, sun
    assert result["closed_regions"] >= 5
    assert result["orientation"] == "landscape"


def test_unknown_mode_rejected(images, cfg, tmp_path):
    with pytest.raises(ValueError):
        to_lineart(images / "clipart.png", tmp_path / "x.png", "sketch", cfg["profiles"]["easy"])


def _runs(row):
    """Number of separate ink runs along a scan line."""
    ink = (row < 128).astype(np.int8)
    return int((np.diff(np.concatenate([[0], ink])) == 1).sum())


def test_convert_bold_colored_outline_becomes_one_line(cfg, tmp_path):
    # A small cartoon: yellow body with a bold brown (not black) outline, the kind
    # that used to come out as a double contour.
    img = np.full((300, 300, 3), 255, np.uint8)
    cv2.circle(img, (150, 150), 110, (90, 40, 30), -1)
    cv2.circle(img, (150, 150), 96, (250, 230, 140), -1)
    cv2.circle(img, (120, 130), 8, (20, 20, 20), -1)      # eyes
    cv2.circle(img, (180, 130), 8, (20, 20, 20), -1)
    src = tmp_path / "bold.png"
    Image.fromarray(img).save(src)

    profile = cfg["profiles"]["medium"]
    result = to_lineart(src, tmp_path / "out.png", "convert", profile)
    px = _pixels(tmp_path / "out.png")
    h, w = px.shape
    lo, hi = profile["line_px"]
    assert lo * 0.8 <= result["line_width_px"] <= hi * 1.2
    # Across the middle, below the eyes: left outline, right outline, nothing else.
    assert _runs(px[int(h * 0.75)]) == 2
    # The eyes stay solid dots inside the body.
    eye_row = px[int(h * (130 - 40) / 220)]
    assert _runs(eye_row) == 4
