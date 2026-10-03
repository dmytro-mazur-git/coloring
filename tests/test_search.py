import pytest

import coloring_kit.search.brave as brave
import coloring_kit.search.openverse as openverse
import coloring_kit.search.serpapi as serpapi
from coloring_kit.search import search


class _Json:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


def _capture(module, monkeypatch, data):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(kwargs)
        return _Json(data)

    monkeypatch.setattr(module, "get", fake_get)
    return calls


@pytest.fixture
def no_keys(monkeypatch):
    for var in ("SERPAPI_API_KEY", "BRAVE_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_serpapi_uses_lineart_filter_and_parses(monkeypatch, cfg, no_keys):
    monkeypatch.setenv("SERPAPI_API_KEY", "k")
    calls = _capture(serpapi, monkeypatch, {"images_results": [
        {"original": "https://x.test/cow.png", "link": "https://x.test/cow", "title": "Cow",
         "original_width": 900, "original_height": 1200, "thumbnail": "https://t/1"},
        {"title": "no original"},
    ]})
    res = search("cow coloring page", "coloring", 10, cfg)
    assert [c.url for c in res] == ["https://x.test/cow.png"]
    assert res[0].provider == "serpapi" and res[0].source_page == "https://x.test/cow"
    assert calls[0]["params"]["tbs"] == "itp:lineart" and calls[0]["params"]["safe"] == "active"


def test_brave_parses_properties(monkeypatch, cfg, no_keys):
    monkeypatch.setenv("BRAVE_API_KEY", "k")
    calls = _capture(brave, monkeypatch, {"results": [
        {"url": "https://y.test/page", "title": "Cow", "properties": {"url": "https://y.test/cow.jpg"},
         "thumbnail": {"src": "https://t/2"}},
    ]})
    res = search("cow clipart", "image", 10, cfg)
    assert res[0].url == "https://y.test/cow.jpg" and res[0].provider == "brave"
    assert calls[0]["headers"]["X-Subscription-Token"] == "k"
    assert calls[0]["params"]["safesearch"] == "strict"


def test_falls_back_to_openverse_without_keys(monkeypatch, cfg, no_keys):
    calls = _capture(openverse, monkeypatch, {"results": [
        {"url": "https://o.test/a.png", "title": "Cow clipart", "foreign_landing_url": "https://o.test/a"},
        {"url": "https://o.test/b.png", "title": "Mature", "mature": True},
    ]})
    res = search("cow clipart", "image", 50, cfg)
    assert [c.url for c in res] == ["https://o.test/a.png"]
    assert calls[0]["params"]["page_size"] == 20 and calls[0]["params"]["mature"] == "false"


def test_blocked_words_filter_titles(monkeypatch, cfg, no_keys):
    _capture(openverse, monkeypatch, {"results": [
        {"url": "https://o.test/a.png", "title": "Scary zombie cow"},
        {"url": "https://o.test/b.png", "title": "Happy cow"},
    ]})
    blocked = {**cfg, "search": {**cfg["search"], "blocked_words": ["zombie"]}}
    assert [c.url for c in search("cow", "image", 10, blocked)] == ["https://o.test/b.png"]


def test_provider_errors_are_skipped(monkeypatch, cfg, no_keys):
    from coloring_kit.http import HttpError

    def fail(url, **kwargs):
        raise HttpError("down")

    monkeypatch.setattr(openverse, "get", fail)
    assert search("cow", "image", 10, cfg) == []
