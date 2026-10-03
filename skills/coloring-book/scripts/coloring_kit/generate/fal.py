"""fal.ai (Flux models)."""

from __future__ import annotations

import os

from . import ProviderUnavailable


class FalProvider:
    name = "fal"

    def __init__(self, options: dict) -> None:
        self.options = options
        self.api_key = os.environ.get("FAL_KEY")
        if not self.api_key:
            raise ProviderUnavailable("FAL_KEY is not set")

    def generate(self, prompt: str, size: tuple[int, int], n: int = 1) -> list[bytes]:
        raise NotImplementedError
