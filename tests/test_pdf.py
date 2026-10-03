import json

import pytest
from reportlab.lib.pagesizes import A4

from conftest import write_json
from coloring_kit.job import init_job
from coloring_kit.lineart import to_lineart
from coloring_kit.models import JobSpec
from coloring_kit.pdf import build_pdf

SPEC = {
    "request": "смайлик і будиночок", "language": "uk", "mode": "set", "difficulty": "easy",
    "captions": True, "cover": True, "title": "Мої розмальовки",
    "pages": [{"n": 1, "subject": "smiley", "caption": "Смайлик"},
              {"n": 2, "subject": "house", "caption": "Будиночок"},
              {"n": 3, "subject": "noise", "caption": "Шум"}],
}


@pytest.fixture
def job(images, cfg, tmp_path):
    created = init_job(JobSpec.from_dict(json.loads(json.dumps(SPEC))), tmp_path, cfg["max_pages"])
    job_dir = tmp_path / created["job_dir"]
    easy = cfg["profiles"]["easy"]
    to_lineart(images / "coloring.png", job_dir / "pages/01/final.png", "cleanup", easy)
    to_lineart(images / "clipart.png", job_dir / "pages/02/final.png", "convert", easy)

    def update(n, **fields):
        path = job_dir / f"pages/{n:02d}/page.json"
        write_json(path, {**json.loads(path.read_text()), **fields})

    update(1, status="accepted", final={"path": "final.png", "origin": "found",
                                         "source_page": "https://coloring.example.com/smiley"})
    update(2, status="accepted", final={"path": "final.png", "origin": "converted",
                                         "source_url": "https://img.example.org/house.png"})
    update(3, status="failed")
    return job_dir


def test_job_dir_keeps_cyrillic_title(job):
    assert "мої-розмальовки" in job.name


def test_pdf_pages_orientation_and_report(job, cfg):
    from pypdf import PdfReader

    out = build_pdf(job, cfg)
    reader = PdfReader(out)
    sizes = [(round(float(p.mediabox.width)), round(float(p.mediabox.height))) for p in reader.pages]
    a4 = (round(A4[0]), round(A4[1]))
    assert sizes == [a4, a4, a4[::-1]]          # cover, portrait smiley, landscape house

    text = "".join(p.extract_text() for p in reader.pages)
    assert "Смайлик" in text and "Будиночок" in text
    assert "coloring.example.com" in text and "img.example.org" in text

    report = (job / "report.md").read_text()
    assert "пропущено" in report
    state = json.loads((job / "job.json").read_text())
    assert state["status"] == "done" and state["included"] == [1, 2] and state["skipped"] == [3]


def test_rejected_page_is_skipped(job, cfg):
    path = job / "pages/02/page.json"
    write_json(path, {**json.loads(path.read_text()), "inspection": {"verdict": "reject"}})
    build_pdf(job, cfg)
    assert json.loads((job / "job.json").read_text())["included"] == [1]


def test_no_pages_raises(job, cfg):
    for n in (1, 2):
        path = job / f"pages/{n:02d}/page.json"
        write_json(path, {**json.loads(path.read_text()), "status": "failed"})
    with pytest.raises(ValueError):
        build_pdf(job, cfg)


def test_job_stop_records_reason(job):
    from coloring_kit.job import stop_job

    result = stop_job(job, "generation_disabled", [3, 2])
    state = json.loads((job / "job.json").read_text())
    assert state["status"] == "stopped" and state["stop_reason"] == "generation_disabled"
    assert state["unresolved_pages"] == [2, 3] == result["unresolved_pages"]
