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
    """Query providers in order; the first one returning results wins.
    Provider errors are skipped; candidates with blocked words in the title are dropped."""
    from ..http import HttpError

    scfg = cfg["search"]
    safe = scfg["safe_search"] == "strict"
    blocked = [w.lower() for w in scfg.get("blocked_words", [])]
    for name in scfg["providers"]:
        try:
            results = get_provider(name).search(query, kind, limit, safe)
        except (ProviderUnavailable, HttpError, ValueError):
            continue
        results = [c for c in results if not any(w in (c.title or "").lower() for w in blocked)]
        if results:
            return results
    return []
