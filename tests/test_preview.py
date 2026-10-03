import json

import pytest
from PIL import Image

from conftest import write_json
from coloring_kit.job import init_job
from coloring_kit.lineart import to_lineart
from coloring_kit.models import JobSpec
from coloring_kit.preview import build_sheet, select_candidate

SPEC = {"request": "Малюк із Saja Boys, спочатку покажи", "language": "uk", "mode": "variants",
        "difficulty": "medium", "preview": True,
        "pages": [{"n": 1, "subject": "Baby from Saja Boys", "caption": "Малюк",
                   "character": "Baby from Saja Boys (KPop Demon Hunters)"}]}


@pytest.fixture
def page(images, cfg, tmp_path):
    created = init_job(JobSpec.from_dict(json.loads(json.dumps(SPEC))), tmp_path, cfg["max_pages"])
    page_json = tmp_path / created["pages"][0]
    page_dir = page_json.parent
    (page_dir / "ref").mkdir()
    Image.open(images / "clipart.png").save(page_dir / "ref" / "ref.png")
    converted = page_dir / "conv_1.png"
    to_lineart(images / "clipart.png", converted, "convert", cfg["profiles"]["medium"])
    write_json(page_dir / "candidates.json", {
        "stage": "stage1", "reference": "ref/ref.png",
        "candidates": [
            {"n": 1, "path": str(images / "coloring.png"), "mode": "cleanup",
             "source_url": "https://a.test/baby.png", "source_page": "https://a.test/kpop",
             "why": "file baby.png", "likeness": "high", "note": ""},
            {"n": 2, "path": "conv_1.png", "mode": "ready",
             "source_url": "https://b.test/x.png", "source_page": "https://b.test/",
             "why": "alt 'Baby'", "likeness": "medium", "note": ""},
        ]})
    return page_json


def test_spec_fields_reach_page_json(page):
    data = json.loads(page.read_text())
    assert data["preview"] is True
    assert data["character"] == "Baby from Saja Boys (KPop Demon Hunters)"


def test_sheet_has_reference_and_candidates(page):
    out = build_sheet(page.parent)
    with Image.open(out) as im:
        # REF + 2 candidates in one row
        assert im.width > 3 * 360 and im.height < 2 * 460


def test_select_cleans_up_and_records_choice(page, cfg):
    result = select_candidate(page, 1, cfg["profiles"]["medium"])
    data = json.loads(page.read_text())
    assert (page.parent / "final.png").exists() and result["selected"] == 1
    assert data["status"] == "selected" and data["chosen_by_user"] is True
    assert data["final"]["source_url"] == "https://a.test/baby.png"
    assert data["stages"]["stage1"]["chosen"] == 1
    assert data["stages"]["stage1"]["chosen_from"] == "candidates.json"


def test_reselect_keeps_previous_final(page, cfg):
    select_candidate(page, 1, cfg["profiles"]["medium"])
    select_candidate(page, 2, cfg["profiles"]["medium"])
    assert (page.parent / "previous_final_1.png").exists()
    data = json.loads(page.read_text())
    assert data["final"]["source_page"] == "https://b.test/"


def test_select_unknown_number(page, cfg):
    with pytest.raises(ValueError, match="no candidate 7"):
        select_candidate(page, 7, cfg["profiles"]["medium"])
