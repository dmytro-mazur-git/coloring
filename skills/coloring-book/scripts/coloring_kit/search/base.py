from __future__ import annotations

from typing import Protocol

from ..models import Candidate, Kind


class ProviderUnavailable(Exception):
    """Raised when a provider has no API key or is temporarily down."""


class ImageSearchProvider(Protocol):
    name: str

    def search(self, query: str, kind: Kind, limit: int, safe: bool = True) -> list[Candidate]:
        """Return image candidates. `kind` tunes the query/filters (line art vs. any image)."""
        ...


def get_provider(name: str) -> ImageSearchProvider:
    from . import brave, openverse, serpapi

    registry = {"serpapi": serpapi.SerpApiProvider, "brave": brave.BraveProvider,
                "openverse": openverse.OpenverseProvider}
    return registry[name]()


def search(query: str, kind: Kind, limit: int, cfg: dict) -> list[Candidate]:
    """Query providers in order; the first one returning results wins."""
    safe = cfg["search"]["safe_search"] == "strict"
    for name in cfg["search"]["providers"]:
        try:
            results = get_provider(name).search(query, kind, limit, safe)
        except ProviderUnavailable:
            continue
        if results:
            return results
    return []
