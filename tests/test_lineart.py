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
    assert lo * 0.8 <= result["line_width_px"] <= hi * 1.2
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
