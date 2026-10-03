"""Final review without a separate inspector agent: one contact sheet with every page's
final image next to its character reference, plus compact metrics; verdicts are written
back with `job verdict`."""

from __future__ import annotations

import json
from pathlib import Path

from .analyze import analyze
from .preview import contact_sheet


def review_sheet(job_dir: Path, cfg: dict, out: Path | None = None) -> dict:
    pages = [json.loads(p.read_text()) for p in sorted(job_dir.glob("pages/*/page.json"))]
    items, lines, last_ref = [], [], None
    for page in pages:
        page_dir = job_dir / "pages" / f"{page['n']:02d}"
        final = page_dir / ((page.get("final") or {}).get("path") or "final.png")
        if page.get("status") == "failed" or not final.exists():
            lines.append(f"p{page['n']} {page['subject']}: no final image ({page.get('status')})")
            continue
        ref = page.get("reference")
        ref_path = (page_dir / ref) if ref else None
        # One REF tile per character: consecutive pages of the same character share it.
        if ref_path and ref_path.exists() and page.get("character") != last_ref:
            items.append((ref_path, f"REF {page.get('caption') or page['subject']}"[:14], True))
            last_ref = page.get("character")
        items.append((final, f"p{page['n']}", False))

        m = analyze(final, cfg["profiles"][page.get("difficulty", "medium")])
        lines.append(
            f"p{page['n']} {page.get('character') or page['subject']}: L{m.lineart_score:.2f}"
            f" gray{m.gray_ratio:.2f} T{m.text_likelihood:.1f} regions{m.closed_regions}"
            f"{'' if m.fits_profile else ' !fit'}{' user-chosen' if page.get('chosen_by_user') else ''}")

    sheet = contact_sheet(items, out or job_dir / "review_sheet.png", cols=4) if items else None
    return {"sheet": str(sheet) if sheet else None, "pages": lines}


def set_verdict(page_json: Path, accept: bool, reasons: list[str], score: int | None = None) -> dict:
    page = json.loads(page_json.read_text())
    page["inspection"] = {"verdict": "accept" if accept else "reject",
                          "score": score, "reasons": reasons}
    page["status"] = "accepted" if accept else "rejected"
    page_json.write_text(json.dumps(page, ensure_ascii=False, indent=2))
    return {"page": page["n"], "status": page["status"]}
