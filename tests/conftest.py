import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "coloring-book" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from coloring_kit.config import load_config  # noqa: E402


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture(scope="session")
def images(tmp_path_factory):
    """Synthetic inputs: a coloring page (with gray shading), flat clipart, and noise."""
    d = tmp_path_factory.mktemp("images")

    page = np.full((1100, 850, 3), 255, np.uint8)
    cv2.circle(page, (425, 420), 220, (0, 0, 0), 5)
    cv2.circle(page, (345, 370), 40, (0, 0, 0), 5)
    cv2.circle(page, (505, 370), 40, (0, 0, 0), 5)
    cv2.ellipse(page, (425, 500), (90, 45), 0, 0, 180, (0, 0, 0), 5)
    cv2.ellipse(page, (425, 880), (260, 120), 0, 0, 360, (150, 150, 150), -1)
    cv2.ellipse(page, (425, 880), (260, 120), 0, 0, 360, (0, 0, 0), 5)
    cv2.imwrite(str(d / "coloring.png"), page)

    text = page.copy()
    cv2.putText(text, "www.coloring-site.com", (60, 1060), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
    cv2.imwrite(str(d / "watermarked.png"), text)

    art = np.full((900, 1200, 3), (250, 235, 210), np.uint8)
    cv2.rectangle(art, (350, 400), (800, 800), (60, 120, 220), -1)
    cv2.fillPoly(art, [np.array([[300, 400], [575, 180], [850, 400]])], (40, 40, 180))
    cv2.rectangle(art, (520, 600), (630, 800), (30, 70, 120), -1)
    cv2.rectangle(art, (400, 470), (490, 550), (240, 200, 120), -1)
    cv2.circle(art, (1000, 180), 90, (40, 210, 250), -1)
    cv2.imwrite(str(d / "clipart.png"), art)

    rng = np.random.default_rng(1)
    noise = cv2.GaussianBlur(rng.normal(128, 60, (800, 1000, 3)).clip(0, 255).astype(np.uint8), (3, 3), 0)
    cv2.imwrite(str(d / "noise.png"), noise)
    return d


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
