import io
import json

import cv2
import numpy as np
import pytest
from PIL import Image

import coloring_kit.fetch as fetch_mod
from coloring_kit.fetch import extract_images, fetch_many


def _png(draw, size=(700, 900)) -> bytes:
    img = np.full((size[1], size[0], 3), 255, np.uint8)
    draw(img)
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    return buf.getvalue()


SQUARE = _png(lambda i: cv2.rectangle(i, (100, 100), (600, 800), (0, 0, 0), 6))
def _resized_jpeg(png: bytes) -> bytes:
    im = Image.open(io.BytesIO(png)).convert("RGB")
    im = im.resize((im.width * 4 // 5, im.height * 4 // 5))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=60)
    return buf.getvalue()


CIRCLE = _png(lambda i: (cv2.circle(i, (350, 450), 250, (0, 0, 0), 6),
                         cv2.circle(i, (260, 380), 40, (0, 0, 0), 6),
                         cv2.ellipse(i, (350, 560), (110, 50), 0, 0, 180, (0, 0, 0), 6)))
CIRCLE_RESAVED = _resized_jpeg(CIRCLE)
TINY = _png(lambda i: None, size=(120, 120))

FILES = {
    "https://a.test/circle.png": CIRCLE,
    "https://a.test/square.png": SQUARE,
    "https://b.test/circle-copy.png": CIRCLE_RESAVED,
    "https://a.test/tiny.png": TINY,
    "https://a.test/page.html": b"<html>not an image</html>",
    "https://spam.test/circle.png": CIRCLE,
}


@pytest.fixture
def fake_download(monkeypatch):
    def download(url, cfg):
        if url not in FILES:
            raise fetch_mod.HttpError(f"{url}: HTTP 404")
        return FILES[url]
    monkeypatch.setattr(fetch_mod, "_download", download)


@pytest.fixture
def cfg_blocked(cfg):
    return {**cfg, "search": {**cfg["search"], "blocked_domains": ["spam.test"]}}


def test_fetch_many_validates_and_dedups(fake_download, cfg_blocked, tmp_path):
    cands = [{"url": u, "source_page": "https://a.test/cows", "title": "t"} for u in FILES]
    cands.append({"url": "https://a.test/missing.png"})
    results = fetch_many(cands, tmp_path, cfg_blocked)
    by_url = {r["url"]: r for r in results}

    assert "path" in by_url["https://a.test/circle.png"]
    assert "path" in by_url["https://a.test/square.png"]
    assert by_url["https://b.test/circle-copy.png"]["skipped"] == "duplicate"
    assert by_url["https://a.test/tiny.png"]["skipped"].startswith("too small")
    assert by_url["https://a.test/page.html"]["skipped"] == "not a supported image"
    assert by_url["https://spam.test/circle.png"]["skipped"] == "blocked domain"
    assert "404" in by_url["https://a.test/missing.png"]["skipped"]

    index = json.loads((tmp_path / "index.json").read_text())
    assert len(index) == 2 and len(list(tmp_path.glob("*.png"))) == 2
    assert {v["source_page"] for v in index.values()} == {"https://a.test/cows"}


def test_fetch_many_dedups_across_calls_and_excluded(fake_download, cfg, tmp_path):
    first = fetch_many([{"url": "https://a.test/circle.png"}], tmp_path, cfg)
    again = fetch_many([{"url": "https://b.test/circle-copy.png"}], tmp_path, cfg)
    assert again[0]["skipped"] == "duplicate"

    other = tmp_path / "other"
    excluded = fetch_many([{"url": "https://a.test/circle.png"}], other, cfg,
                          exclude_hashes={first[0]["phash"]})
    assert excluded[0]["skipped"] == "duplicate"


HTML = """<html><head>
<meta property="og:image" content="/img/cow-big.jpg">
</head><body>
<img src="/static/logo.png" width="300" height="300">
<img src="/img/tiny.png" width="40" height="40" alt="tiny">
<img src="/img/cow-small.webp" width="550" height="550" alt="Small cow">
<img data-src="/img/lazy-cow.png" src="data:image/gif;base64,R0lGOD" width="800" height="1000" alt="Lazy cow">
<img srcset="/img/s-400.png 400w, /img/s-1200.png 1200w" alt="Srcset cow">
<img src="/_next/image?url=%2Fimg%2Fnext-cow.png&w=640" alt="Next cow">
<a href="/download/cow-print.png">Print</a>
<img src="/img/icon.svg">
</body></html>"""


class _Resp:
    text = HTML
    url = "https://site.test/cows"


def test_extract_images_ranks_and_filters(monkeypatch, cfg):
    monkeypatch.setattr(fetch_mod, "get", lambda *a, **k: _Resp())
    items = extract_images("https://site.test/cows", cfg)
    urls = [i["url"] for i in items]

    assert urls[0] == "https://site.test/img/cow-big.jpg"               # og:image first
    assert urls[1] == "https://site.test/download/cow-print.png"        # direct image link next
    assert urls[2] == "https://site.test/img/lazy-cow.png"              # biggest declared <img>
    assert "https://site.test/img/s-1200.png" in urls                   # largest srcset entry
    assert "https://site.test/img/next-cow.png" in urls                 # unwrapped proxy URL
    assert not any("logo" in u or "tiny" in u or u.endswith(".svg") or u.startswith("data:")
                   for u in urls)
    assert all(i["source_page"] == "https://site.test/cows" for i in items)
