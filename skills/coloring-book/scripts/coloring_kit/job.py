"""Job workspace: output/<date>_<slug>_<id>/ with job.json and pages/NN/page.json."""

from __future__ import annotations

import json
import re
import uuid
from datetime import date
from pathlib import Path

from .models import JobSpec


def _slug(text: str) -> str:
    return re.sub(r"[^\w]+", "-", text.lower()).strip("-_")[:40] or "job"


def init_job(spec: JobSpec, output_dir: Path, max_pages: int) -> dict:
    if not 1 <= len(spec.pages) <= max_pages:
        raise ValueError(f"page count must be 1..{max_pages}, got {len(spec.pages)}")

    name = spec.title or spec.pages[0].subject
    job_dir = output_dir / f"{date.today():%Y-%m-%d}_{_slug(name)}_{uuid.uuid4().hex[:4]}"
    page_paths = []
    for page in spec.pages:
        page_dir = job_dir / "pages" / f"{page.n:02d}"
        (page_dir / "candidates").mkdir(parents=True)
        (page_dir / "thumbs").mkdir()
        page_json = {
            "n": page.n,
            "subject": page.subject,
            "caption": page.caption,
            "difficulty": spec.difficulty,
            "query_hints": page.query_hints,
            "character": page.character,
            "preview": spec.preview,
            "reference": None,
            "exclude_hashes": [],
            "status": "planned",
            "stages": {},
            "final": None,
            "inspection": None,
        }
        path = page_dir / "page.json"
        path.write_text(json.dumps(page_json, ensure_ascii=False, indent=2))
        page_paths.append(str(path.resolve()))

    job = {"spec": _spec_dict(spec), "status": "planned", "pdf": None}
    (job_dir / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2))
    return {"job_dir": str(job_dir.resolve()), "pages": page_paths}


def stop_job(job_dir: Path, reason: str, pages: list[int]) -> dict:
    """Mark the job as stopped (no PDF will be built) and record why."""
    path = job_dir / "job.json"
    job = json.loads(path.read_text())
    job.update(status="stopped", stop_reason=reason, unresolved_pages=sorted(pages), pdf=None)
    path.write_text(json.dumps(job, ensure_ascii=False, indent=2))
    return {"job_dir": str(job_dir.resolve()), "status": "stopped", "reason": reason,
            "unresolved_pages": sorted(pages)}


def _spec_dict(spec: JobSpec) -> dict:
    from .models import to_dict

    return to_dict(spec)
