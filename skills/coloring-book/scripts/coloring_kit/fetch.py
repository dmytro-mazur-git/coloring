"""Download candidates with validation (MIME, size, resolution) and dedup by perceptual hash."""

from __future__ import annotations

from pathlib import Path


def fetch(url: str, out_dir: Path, cfg: dict, exclude_hashes: set[str] = frozenset()) -> dict:
    """Download `url` into `out_dir`.

    Returns {"path": str, "width": int, "height": int, "phash": str} or
    {"skipped": "<reason>"} for not-an-image / too large / too small / duplicate.
    """
    raise NotImplementedError


def extract_images(page_url: str, cfg: dict) -> list[dict]:
    """Fallback for WebSearch results: list <img>/srcset URLs on a page, largest first."""
    raise NotImplementedError
