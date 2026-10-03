"""Data contracts shared by the CLI, the orchestrator skill and the subagents."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Mode = Literal["variants", "set"]
Difficulty = Literal["easy", "medium", "hard"]
Orientation = Literal["auto", "portrait", "landscape"]
Kind = Literal["coloring", "image"]
Origin = Literal["found", "converted", "generated"]


@dataclass
class PageSpec:
    n: int
    subject: str
    caption: str | None = None
    query_hints: list[str] = field(default_factory=list)


@dataclass
class JobSpec:
    request: str
    language: str
    mode: Mode
    difficulty: Difficulty
    pages: list[PageSpec]
    captions: bool = False
    cover: bool = False
    orientation: Orientation = "auto"
    title: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "JobSpec":
        pages = [PageSpec(**p) for p in data.pop("pages")]
        return cls(pages=pages, **data)


@dataclass
class Candidate:
    """One image search result."""

    url: str
    source_page: str | None = None
    thumb_url: str | None = None
    title: str | None = None
    width: int | None = None
    height: int | None = None
    provider: str | None = None


@dataclass
class ImageMetrics:
    """Output of `analyze`. Scores and ratios are 0..1; pixel values are at print scale."""

    width: int
    height: int
    lineart_score: float
    convertibility_score: float
    color_ratio: float          # share of saturated pixels
    gray_ratio: float           # share of mid-gray pixels
    ink_ratio: float            # share of dark (ink) pixels
    line_width_px: float        # median stroke width when fitted to A4 at 300 DPI
    closed_regions: int
    text_likelihood: float      # watermark/text heuristic
    phash: str
    fits_profile: bool


def to_dict(obj) -> dict:
    return asdict(obj)
