"""Brave Image Search API (safesearch=strict)."""

from __future__ import annotations

import os

from ..http import get
from ..models import Candidate, Kind
from .base import ProviderUnavailable

ENDPOINT = "https://api.search.brave.com/res/v1/images/search"


class BraveProvider:
    name = "brave"

    def __init__(self) -> None:
        self.api_key = os.environ.get("BRAVE_API_KEY")
        if not self.api_key:
            raise ProviderUnavailable("BRAVE_API_KEY is not set")

    def search(self, query: str, kind: Kind, limit: int, safe: bool = True) -> list[Candidate]:
        # Brave has no image-type filter: the query wording carries the intent.
        params = {"q": query, "count": min(limit, 100), "safesearch": "strict" if safe else "off"}
        headers = {"X-Subscription-Token": self.api_key, "Accept": "application/json"}
        data = get(ENDPOINT, params=params, headers=headers, timeout=30).json()
        out = []
        for r in data.get("results", [])[:limit]:
            props = r.get("properties") or {}
            url = props.get("url")
            if url:
                out.append(Candidate(url=url, source_page=r.get("url"),
                                     thumb_url=(r.get("thumbnail") or {}).get("src"),
                                     title=r.get("title"), width=props.get("width"),
                                     height=props.get("height"), provider=self.name))
        return out
