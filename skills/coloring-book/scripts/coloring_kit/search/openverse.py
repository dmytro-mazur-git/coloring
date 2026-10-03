"""Openverse API (no key needed); fallback with CC-licensed images."""

from __future__ import annotations

from ..models import Candidate, Kind


class OpenverseProvider:
    name = "openverse"

    def search(self, query: str, kind: Kind, limit: int, safe: bool = True) -> list[Candidate]:
        raise NotImplementedError
