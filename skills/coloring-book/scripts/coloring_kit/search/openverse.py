"""Openverse API (no key needed). Openly licensed images: good for clipart and
illustrations (stage 2), weak for ready coloring pages."""

from __future__ import annotations

from ..http import get
from ..models import Candidate, Kind

ENDPOINT = "https://api.openverse.org/v1/images/"
ANONYMOUS_PAGE_SIZE = 20


class OpenverseProvider:
    name = "openverse"

    def search(self, query: str, kind: Kind, limit: int, safe: bool = True) -> list[Candidate]:
        params = {"q": query, "page_size": min(limit, ANONYMOUS_PAGE_SIZE),
                  "category": "illustration,digitized_artwork"}
        if safe:
            params["mature"] = "false"
        data = get(ENDPOINT, params=params, timeout=30).json()
        return [
            Candidate(url=r["url"], source_page=r.get("foreign_landing_url"),
                      thumb_url=r.get("thumbnail"), title=r.get("title"), width=r.get("width"),
                      height=r.get("height"), provider=self.name)
            for r in data.get("results", [])[:limit]
            if r.get("url") and not r.get("mature")
        ]
