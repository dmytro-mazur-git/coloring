from PIL import Image

from coloring_kit.analyze import analyze, thumbnail


def test_lineart_score_ranks_coloring_page_above_others(images, cfg):
    p = cfg["profiles"]["medium"]
    coloring = analyze(images / "coloring.png", p)
    clipart = analyze(images / "clipart.png", p)
    noise = analyze(images / "noise.png", p)

    threshold = cfg["thresholds"]["lineart_score_min"]
    assert coloring.lineart_score >= threshold
    assert clipart.lineart_score < threshold
    assert noise.lineart_score < threshold


def test_convertibility_prefers_flat_clipart_over_noise(images, cfg):
    p = cfg["profiles"]["medium"]
    clipart = analyze(images / "clipart.png", p)
    noise = analyze(images / "noise.png", p)
    assert clipart.convertibility_score >= cfg["thresholds"]["convertibility_score_min"]
    assert noise.convertibility_score < cfg["thresholds"]["convertibility_score_min"]


def test_line_width_ignores_gray_shading(images, cfg):
    m = analyze(images / "coloring.png", cfg["profiles"]["medium"])
    # 5-6 px strokes on an 850x1100 page scale ~2.6x to A4 at 300 DPI.
    assert 10 <= m.line_width_px <= 20
    assert m.closed_regions == 4    # face, two eyes, ellipse (the smile is open)


def test_text_likelihood_flags_watermark(images, cfg):
    p = cfg["profiles"]["medium"]
    assert analyze(images / "watermarked.png", p).text_likelihood >= 0.5
    assert analyze(images / "coloring.png", p).text_likelihood == 0


def test_thumbnail_is_bounded(images, tmp_path):
    out = thumbnail(images / "clipart.png", 256, tmp_path / "t.png")
    with Image.open(out) as im:
        assert max(im.size) == 256


def test_thumbnail_puts_transparency_on_white(tmp_path):
    src = tmp_path / "a.png"
    Image.new("RGBA", (600, 400), (0, 0, 0, 0)).save(src)
    with Image.open(thumbnail(src, 128, tmp_path / "t.png")) as im:
        assert im.convert("L").getpixel((5, 5)) == 255
