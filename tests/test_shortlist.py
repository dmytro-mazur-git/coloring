import json
import shutil

import pytest

import coloring_kit.fetch as fetch_mod
from coloring_kit.job import init_job
from coloring_kit.models import JobSpec
from coloring_kit.preview import make_candidates, select_candidate
from coloring_kit.review import review_sheet, set_verdict
from coloring_kit.shortlist import shortlist

SPEC = {"request": "t", "language": "uk", "mode": "variants", "difficulty": "medium",
        "pages": [{"n": 1, "subject": "smiley"}, {"n": 2, "subject": "smiley"}]}


@pytest.fixture
def job(images, cfg, tmp_path, monkeypatch):
    files = {
        "https://s.test/img/smiley-coloring.png": (images / "coloring.png").read_bytes(),
        "https://s.test/img/house-clipart.png": (images / "clipart.png").read_bytes(),
        "https://s.test/img/noise-photo.png": (images / "noise.png").read_bytes(),
        "https://s.test/img/smiley-watermarked.png": (images / "watermarked.png").read_bytes(),
    }
    monkeypatch.setattr(fetch_mod, "_download", lambda url, cfg: files[url])
    created = init_job(JobSpec.from_dict(json.loads(json.dumps(SPEC))), tmp_path, cfg["max_pages"])
    lst = tmp_path / "site.json"
    lst.write_text(json.dumps([{"url": u, "source_page": "https://s.test/", "title": ""} for u in files]))
    return [tmp_path / p for p in created["pages"]], lst


def test_shortlist_coloring_filters_and_ranks(job, cfg):
    (page1, _), lst = job
    out = shortlist(page1, [lst], cfg, "coloring")
    data = json.loads((page1.parent / "shortlist.json").read_text())
    urls = [c["source_url"] for c in data["candidates"]]
    # Clean coloring page first, the watermarked copy is a near-duplicate or ranked lower,
    # clipart and noise are not line art.
    assert urls[0].endswith("smiley-coloring.png")
    assert not any("clipart" in u or "noise" in u for u in urls)
    assert out["sheet"] and len(out["rows"]) == out["shortlisted"]


def test_shortlist_match_filters_before_download(job, cfg):
    (page1, _), lst = job
    out = shortlist(page1, [lst], cfg, "image", match=["house"], convert=1)
    assert out["skipped"]["no name match"] == 3
    data = json.loads((page1.parent / "shortlist.json").read_text())
    assert data["stage"] == "stage2"
    assert data["candidates"][0]["mode"] == "ready"           # converted for the sheet
    assert (page1.parent / "conv_1.png").exists()


def test_shortlist_rerun_reuses_downloads(job, cfg):
    (page1, _), lst = job
    first = shortlist(page1, [lst], cfg, "coloring")
    again = shortlist(page1, [lst], cfg, "coloring")
    assert again["shortlisted"] == first["shortlisted"] and "duplicate" not in again["skipped"]


def test_agent_pick_from_shortlist(job, cfg):
    (page1, _), lst = job
    shortlist(page1, [lst], cfg, "coloring")
    select_candidate(page1, 1, cfg["profiles"]["medium"], source="shortlist", by_user=False)
    data = json.loads(page1.read_text())
    assert data["chosen_by_user"] is False and data["stages"]["stage1"]["chosen_from"] == "shortlist.json"


def test_candidates_from_shortlist_for_two_pages(job, cfg):
    (page1, page2), lst = job
    shortlist(page1, [lst], cfg, "image", convert=2)
    n = len(json.loads((page1.parent / "shortlist.json").read_text())["candidates"])
    keep = list(range(n, 0, -1))
    out = make_candidates(page1, keep, {keep[0]: "high"}, {keep[0]: "hair ✓"}, [page2])
    for page in (page1, page2):
        data = json.loads((page.parent / "candidates.json").read_text())
        assert [c["shortlist_n"] for c in data["candidates"]] == keep
        assert data["candidates"][0]["likeness"] == "high"
        assert (page.parent / "candidates_sheet.png").exists()
    select_candidate(page2, 1, cfg["profiles"]["medium"])
    assert (page2.parent / "final.png").exists()
    assert out["candidates"] == n


def test_review_sheet_and_verdict(job, cfg, images):
    (page1, page2), _ = job
    shutil.copy(images / "coloring.png", page1.parent / "final.png")
    out = review_sheet(page1.parent.parent.parent, cfg)
    assert out["sheet"] and out["pages"][0].startswith("p1 ") and "no final image" in out["pages"][1]
    set_verdict(page1, False, ["text visible"], 3)
    data = json.loads(page1.read_text())
    assert data["status"] == "rejected" and data["inspection"]["reasons"] == ["text visible"]
