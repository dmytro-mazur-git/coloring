"""A4 PDF layout: 300 DPI, 10 mm margins, auto orientation, optional captions/cover,
small attribution footer per page (source domain or generation provider)."""

from __future__ import annotations

from pathlib import Path


def build_pdf(job_dir: Path, cfg: dict) -> Path:
    """Read job.json and accepted pages' final.png; write <job_dir>/<slug>.pdf and report.md.

    Pages with status `failed` or a `reject` verdict are skipped.
    """
    raise NotImplementedError
