"""Brave Image Search API (safesearch=strict)."""

from __future__ import annotations

import os

from ..models import Candidate, Kind
from .base import ProviderUnavailable


class BraveProvider:
    name = "brave"

    def __init__(self) -> None:
        self.api_key = os.environ.get("BRAVE_API_KEY") if "BRAVE_API_KEY" else None
        if "BRAVE_API_KEY" and not self.api_key:
            raise ProviderUnavailable("BRAVE_API_KEY is not set")

    def search(self, query: str, kind: Kind, limit: int, safe: bool = True) -> list[Candidate]:
        raise NotImplementedError
