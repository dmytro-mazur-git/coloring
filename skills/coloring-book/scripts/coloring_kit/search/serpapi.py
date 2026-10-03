"""Google Images via SerpAPI (engine=google_images, safe=active; for kind=coloring add tbs=ic:gray)."""

from __future__ import annotations

import os

from ..models import Candidate, Kind
from .base import ProviderUnavailable


class SerpApiProvider:
    name = "serpapi"

    def __init__(self) -> None:
        self.api_key = os.environ.get("SERPAPI_API_KEY") if "SERPAPI_API_KEY" else None
        if "SERPAPI_API_KEY" and not self.api_key:
            raise ProviderUnavailable("SERPAPI_API_KEY is not set")

    def search(self, query: str, kind: Kind, limit: int, safe: bool = True) -> list[Candidate]:
        raise NotImplementedError
