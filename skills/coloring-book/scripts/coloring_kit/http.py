"""HTTP GET with retries on transient failures (connection errors, 429, 5xx)."""

from __future__ import annotations

import time

import requests

RETRY_STATUS = {429, 500, 502, 503, 504}
DEFAULT_UA = "Mozilla/5.0 (compatible; coloring-plugin/0.2; personal use)"


class HttpError(Exception):
    pass


def get(url: str, *, params: dict | None = None, headers: dict | None = None,
        timeout: float = 20, retries: int = 3, stream: bool = False,
        user_agent: str | None = None) -> requests.Response:
    hdrs = {"User-Agent": user_agent or DEFAULT_UA, **(headers or {})}
    delay = 1.0
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=hdrs, timeout=timeout, stream=stream)
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise HttpError(f"{url}: {e}") from e
        else:
            if resp.status_code not in RETRY_STATUS or attempt == retries - 1:
                if resp.status_code >= 400:
                    raise HttpError(f"{url}: HTTP {resp.status_code}")
                return resp
            resp.close()
        time.sleep(delay)
        delay *= 2
    raise HttpError(f"{url}: retries exhausted")
