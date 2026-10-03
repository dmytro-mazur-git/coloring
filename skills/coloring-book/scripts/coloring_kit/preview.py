"""Candidate preview for the user: contact sheet from a page's candidates.json and
applying the user's choice to the page.

candidates.json (in the page dir), written by a stage subagent in preview mode:
{
  "stage": "stage1" | "stage2",
  "reference": "ref/ref.png" | null,          # official look of a character, if any
  "candidates": [
    {"n": 1, "path": "candidates/abc.png",    # relative to the page dir, or absolute
     "mode": "cleanup" | "ready",             # cleanup: found line art; ready: already converted
     "source_url": "...", "source_page": "...",
     "why": "why it matches the subject", "likeness": "high" | "medium" | "low" | null,
     "note": "..."}
  ]
}
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .imaging import load_rgb, perceptual_hash
from .lineart import to_lineart

SKILL_DIR = Path(__file__).resolve().parents[2]
TILE_W, TILE_H, GAP = 360, 460, 12
MAX_TILES = 9
REF_FILL = (255, 221, 87)
BORDER = (190, 190, 190)


def _resolve(page_dir: Path, path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else page_dir / p


def load_candidates(page_dir: Path) -> dict:
    path = page_dir / "candidates.json"
    if not path.exists():
        raise ValueError(f"no candidates.json in {page_dir}")
    return json.loads(path.read_text())


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(SKILL_DIR / "assets" / "fonts" / "DejaVuSans-Bold.ttf"), size)
    except OSError:
        return ImageFont.load_default()


def _tile(image: Path, label: str, highlight: bool) -> Image.Image:
    tile = Image.new("RGB", (TILE_W, TILE_H), "white")
    im = Image.fromarray(load_rgb(image))
    im.thumbnail((TILE_W - 20, TILE_H - 20), Image.LANCZOS)
    tile.paste(im, ((TILE_W - im.width) // 2, (TILE_H - im.height) // 2))

    draw = ImageDraw.Draw(tile)
    font = _font(44)
    box = draw.textbbox((0, 0), label, font=font)
    w, h = box[2] - box[0] + 24, box[3] - box[1] + 20
    draw.rectangle((4, 4, 4 + w, 4 + h), fill=REF_FILL if highlight else "white",
                   outline=(30, 30, 30), width=3)
    draw.text((4 + 12 - box[0], 4 + 10 - box[1]), label, fill=(20, 20, 20), font=font)
    draw.rectangle((0, 0, TILE_W - 1, TILE_H - 1), outline=BORDER, width=2)
    return tile


def build_sheet(page_dir: Path, out: Path | None = None) -> Path:
    """Contact sheet: reference tile ("REF") first if present, then candidates by number."""
    data = load_candidates(page_dir)
    tiles = []
    if data.get("reference"):
        tiles.append(_tile(_resolve(page_dir, data["reference"]), "REF", highlight=True))
    for c in sorted(data["candidates"], key=lambda c: c["n"])[:MAX_TILES]:
        tiles.append(_tile(_resolve(page_dir, c["path"]), str(c["n"]), highlight=False))
    if not tiles:
        raise ValueError("candidates.json lists no candidates")

    cols = min(len(tiles), 5)
    rows = -(-len(tiles) // cols)
    sheet = Image.new("RGB", (cols * TILE_W + (cols + 1) * GAP, rows * TILE_H + (rows + 1) * GAP),
                      (225, 225, 225))
    for i, tile in enumerate(tiles):
        r, c = divmod(i, cols)
        sheet.paste(tile, (GAP + c * (TILE_W + GAP), GAP + r * (TILE_H + GAP)))

    out = out or page_dir / "candidates_sheet.png"
    sheet.save(out, optimize=True)
    return out


def select_candidate(page_json: Path, n: int, profile: dict) -> dict:
    """Make candidate `n` the page's final image (user's choice) and update page.json."""
    page_dir = page_json.parent
    data = load_candidates(page_dir)
    chosen = next((c for c in data["candidates"] if c["n"] == n), None)
    if chosen is None:
        raise ValueError(f"no candidate {n}; available: {[c['n'] for c in data['candidates']]}")

    final = page_dir / "final.png"
    if final.exists():
        # Keep what was there before (e.g. an earlier pick the user did not like).
        k = 1
        while (page_dir / f"previous_final_{k}.png").exists():
            k += 1
        final.rename(page_dir / f"previous_final_{k}.png")

    src = _resolve(page_dir, chosen["path"])
    if chosen.get("mode") == "ready":
        shutil.copyfile(src, final)
        metrics = {"path": str(final)}
    else:
        metrics = to_lineart(src, final, "cleanup", profile)

    with Image.open(final) as im:
        phash = perceptual_hash(im)

    stage = data.get("stage", "stage1")
    page = json.loads(page_json.read_text())
    page.setdefault("stages", {}).setdefault(stage, {}).update(
        status="found", chosen_by_user=n, candidates="candidates.json")
    page["final"] = {
        "path": "final.png",
        "origin": "found" if stage == "stage1" else "converted",
        "source_url": chosen.get("source_url"),
        "source_page": chosen.get("source_page"),
        "provider": None,
        "prompt": None,
        "phash": phash,
    }
    page["status"] = "selected"
    page["chosen_by_user"] = True
    page_json.write_text(json.dumps(page, ensure_ascii=False, indent=2))
    return {"page": page["n"], "selected": n, **metrics, "phash": phash}
