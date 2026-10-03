"""Configuration loading: skill defaults merged with an optional user override."""

from __future__ import annotations

from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config.yaml"
USER_CONFIG = Path.home() / ".config" / "coloring" / "config.yaml"


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path | None = None) -> dict[str, Any]:
    import yaml

    cfg = yaml.safe_load(DEFAULT_CONFIG.read_text()) or {}
    for extra in (USER_CONFIG, path):
        if extra and extra.exists():
            cfg = _merge(cfg, yaml.safe_load(extra.read_text()) or {})
    return cfg
