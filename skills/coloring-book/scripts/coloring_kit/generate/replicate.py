"""Replicate (e.g. a Flux model with a line-art LoRA)."""

from __future__ import annotations

import os

from . import ProviderUnavailable


class ReplicateProvider:
    name = "replicate"

    def __init__(self, options: dict) -> None:
        self.options = options
        self.api_key = os.environ.get("REPLICATE_API_TOKEN")
        if not self.api_key:
            raise ProviderUnavailable("REPLICATE_API_TOKEN is not set")

    def generate(self, prompt: str, size: tuple[int, int], n: int = 1) -> list[bytes]:
        raise NotImplementedError
