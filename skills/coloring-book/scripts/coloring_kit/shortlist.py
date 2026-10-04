"""One call instead of ~10 agent steps: fetch candidate lists, analyze, filter, rank,
optionally convert (stage 2), and build a numbered contact sheet.

Writes `<page dir>/shortlist.json` (same shape as candidates.json, see preview.py) and
`<page dir>/shortlist_sheet.png`, and returns a compact summary for the agent.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from .analyze import analyze
from .fetch import fetch_many
from .lineart import to_lineart
from .preview import build_sheet

LINEART_IS_READY = 0.7      # an "image" candidate this line-art-like is cleaned, not converted
TEXT_PENALTY = 0.3          # ranking penalty per unit of text_likelihood (watermarks)


def _reason(text: str) -> str:
    """Group fetch skip messages: 'too small 120x120' -> 'too small', HTTP errors -> 'download error'."""
    for prefix in ("too small", "too large", "duplicate", "blocked domain", "not a supported image"):
        if text.startswith(prefix):
            return prefix
    return "download error"


def _merge(lists: list[Path]) -> list[dict]:
    seen, out = set(), []
    for path in lists:
        for c in json.loads(Path(path).read_text()):
            if c.get("url") and c["url"] not in seen:
                seen.add(c["url"])
                out.append(c)
    return out


def _matches(c: dict, terms: list[str]) -> bool:
    """Any term in the image file name, its URL path or title (case-insensitive)."""
    text = f"{urlparse(c['url']).path} {c.get('title') or ''}".lower()
    return any(t.lower() in text for t in terms)


def shortlist(page_json: Path, lists: list[Path], cfg: dict, kind: str, top: int = 8,
              exclude: set[str] = frozenset(), convert: int = 0, limit: int = 40,
              match: list[str] | None = None) -> dict:
    # Absolute paths: shortlist.json is later resolved against the page dir, not the cwd.
    page_json = page_json.resolve()
    page_dir = page_json.parent
    page = json.loads(page_json.read_text())
    profile = cfg["profiles"][page.get("difficulty", "medium")]
    exclude = set(exclude) | set(page.get("exclude_hashes", []))

    candidates = _merge(lists)
    skipped = Counter()
    if match:
        kept = [c for c in candidates if _matches(c, match)]
        skipped["no name match"] = len(candidates) - len(kept)
        candidates = kept
    candidates = candidates[:limit]
    results = fetch_many(candidates, page_dir / "candidates", cfg, exclude)
    skipped.update(_reason(r["skipped"]) for r in results if "skipped" in r)

    th = cfg["thresholds"]
    rows = []
    for r in (r for r in results if "path" in r):
        try:
            m = analyze(Path(r["path"]), profile)
        except Exception:  # noqa: BLE001 - a broken file is just not a candidate
            skipped["unreadable"] += 1
            continue
        if kind == "coloring":
            if m.lineart_score < th["lineart_score_min"]:
                skipped["not line art"] += 1
                continue
            rank, mode = m.lineart_score, "cleanup"
        else:
            if m.convertibility_score < th["convertibility_score_min"]:
                skipped["hard to convert"] += 1
                continue
            mode = "cleanup" if m.lineart_score >= LINEART_IS_READY else "convert"
            rank = m.convertibility_score
        rows.append({
            "path": r["path"], "mode": mode, "source_url": r["url"],
            "source_page": r.get("source_page"), "title": r.get("title"),
            "lineart": m.lineart_score, "convertibility": m.convertibility_score,
            "text": m.text_likelihood, "fits_profile": m.fits_profile, "phash": m.phash,
            "_rank": rank - TEXT_PENALTY * m.text_likelihood,
        })

    rows.sort(key=lambda x: -x["_rank"])
    rows = rows[:top]
    for i, row in enumerate(rows, 1):
        row.pop("_rank")
        row["n"] = i
        if row["mode"] == "convert" and i <= convert:
            conv = page_dir / f"conv_{i}.png"
            to_lineart(Path(row["path"]), conv, "convert", profile)
            row.update(original=row["path"], path=str(conv), mode="ready")

    stage = "stage1" if kind == "coloring" else "stage2"
    data = {"stage": stage, "reference": page.get("reference"), "candidates": rows}
    (page_dir / "shortlist.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    sheet = build_sheet(page_dir, name="shortlist.json") if rows else None

    return {
        "sheet": str(sheet) if sheet else None,
        "shortlisted": len(rows),
        "fetched": sum(1 for r in results if "path" in r),
        "skipped": dict(skipped),
        "rows": [
            f"{x['n']} {urlparse(x['source_url']).netloc} L{x['lineart']:.2f} C{x['convertibility']:.2f}"
            f" T{x['text']:.1f}{'' if x['fits_profile'] else ' !fit'} {x['mode']}"
            f" | {(x.get('title') or '')[:50]}"
            for x in rows
        ],
    }
