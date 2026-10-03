"""Google Images via SerpAPI (engine=google_images, safe=active).

kind=coloring uses Google's "line drawing" type filter, kind=image the "clip art" one:
clipart converts to line art far better than photos.
"""

from __future__ import annotations

import os

from ..http import get
from ..models import Candidate, Kind
from .base import ProviderUnavailable

ENDPOINT = "https://serpapi.com/search.json"
TYPE_FILTER = {"coloring": "itp:lineart", "image": "itp:clipart"}


class SerpApiProvider:
    name = "serpapi"

    def __init__(self) -> None:
        self.api_key = os.environ.get("SERPAPI_API_KEY")
        if not self.api_key:
            raise ProviderUnavailable("SERPAPI_API_KEY is not set")

    def search(self, query: str, kind: Kind, limit: int, safe: bool = True) -> list[Candidate]:
        params = {"engine": "google_images", "q": query, "api_key": self.api_key,
                  "tbs": TYPE_FILTER[kind], "safe": "active" if safe else "off"}
        data = get(ENDPOINT, params=params, timeout=30).json()
        return [
            Candidate(url=r["original"], source_page=r.get("link"), thumb_url=r.get("thumbnail"),
                      title=r.get("title"), width=r.get("original_width"),
                      height=r.get("original_height"), provider=self.name)
            for r in data.get("images_results", [])[:limit] if r.get("original")
        ]
