"""Image generation providers. Tried in the order given by config `generate.providers`."""

from __future__ import annotations

from typing import Protocol


class ProviderUnavailable(Exception):
    pass


class ImageGenProvider(Protocol):
    name: str

    def generate(self, prompt: str, size: tuple[int, int], n: int = 1) -> list[bytes]:
        """Return PNG bytes for each generated image."""
        ...


def get_provider(name: str, cfg: dict) -> ImageGenProvider:
    from . import fal, openai, replicate

    registry = {"openai": openai.OpenAIProvider, "replicate": replicate.ReplicateProvider,
                "fal": fal.FalProvider}
    return registry[name](cfg.get(name, {}))
