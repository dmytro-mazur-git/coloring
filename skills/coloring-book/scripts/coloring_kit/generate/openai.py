"""OpenAI Images API (gpt-image-1 by default)."""

from __future__ import annotations

import os

from . import ProviderUnavailable


class OpenAIProvider:
    name = "openai"

    def __init__(self, options: dict) -> None:
        self.options = options
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ProviderUnavailable("OPENAI_API_KEY is not set")

    def generate(self, prompt: str, size: tuple[int, int], n: int = 1) -> list[bytes]:
        raise NotImplementedError
