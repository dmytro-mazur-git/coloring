"""Cheap pixel metrics used to filter candidates before any vision-LLM look."""

from __future__ import annotations

from pathlib import Path

from .models import ImageMetrics


def analyze(image: Path, profile: dict) -> ImageMetrics:
    """Compute metrics for one image.

    - lineart_score: how close the image already is to black-on-white line art
      (bimodal histogram, low color/gray ratio, thin strokes).
    - convertibility_score: how well it will convert (uniform border/background,
      subject contrast, few flat colors, sharpness, subject fill ratio).
    - closed_regions / line_width_px: compared against `profile` -> fits_profile.
    - text_likelihood: MSER/stroke-width heuristic for watermarks and text.
    """
    raise NotImplementedError


def thumbnail(image: Path, max_px: int) -> Path:
    """Write <page dir>/thumbs/<name>.png no larger than max_px for vision review."""
    raise NotImplementedError
