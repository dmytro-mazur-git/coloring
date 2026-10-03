"""Download candidates with validation (type, size, resolution) and near-duplicate
detection by perceptual hash; list images found on a web page.

Each download directory keeps an `index.json` ({file: {url, source_page, title, phash}})
so provenance survives and duplicates are detected across calls.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import imagehash
from PIL import Image

from .http import HttpError, get
from .imaging import perceptual_hash

DUPLICATE_DISTANCE = 10       # pHash Hamming distance treated as the same picture
FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp", "GIF": "gif", "BMP": "bmp"}
INDEX = "index.json"
JUNK_URL = re.compile(r"logo|icon|avatar|sprite|banner|favicon|badge|/ads?/|pixel|placeholder|spinner",
                      re.IGNORECASE)
IMAGE_EXT = re.compile(r"\.(png|jpe?g|webp|gif|bmp)(\?|$)", re.IGNORECASE)


def _blocked(url: str, cfg: dict) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == d or host.endswith("." + d) for d in cfg["search"].get("blocked_domains", []))


def _load_index(out_dir: Path) -> dict:
    path = out_dir / INDEX
    return json.loads(path.read_text()) if path.exists() else {}


def _download(url: str, cfg: dict) -> bytes:
    fc = cfg["fetch"]
    resp = get(url, timeout=fc["timeout_s"], stream=True, user_agent=fc["user_agent"])
    with resp:
        declared = int(resp.headers.get("Content-Length") or 0)
        if declared > fc["max_bytes"]:
            raise ValueError(f"too large ({declared} bytes)")
        data = bytearray()
        for chunk in resp.iter_content(64 * 1024):
            data += chunk
            if len(data) > fc["max_bytes"]:
                raise ValueError("too large")
    return bytes(data)


def _check(data: bytes, cfg: dict) -> tuple[Image.Image, str]:
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as e:  # noqa: BLE001 - any decoder error means "not an image we can use"
        raise ValueError("not a supported image") from e
    if im.format not in FORMATS:
        raise ValueError(f"unsupported format {im.format}")
    if min(im.size) < cfg["fetch"]["min_short_side_px"]:
        raise ValueError(f"too small {im.size[0]}x{im.size[1]}")
    return im, FORMATS[im.format]


def _is_duplicate(phash: str, known: list[str]) -> bool:
    h = imagehash.hex_to_hash(phash)
    return any(h - imagehash.hex_to_hash(k) <= DUPLICATE_DISTANCE for k in known)


def fetch_one(candidate: dict, out_dir: Path, cfg: dict, known_hashes: list[str]) -> dict:
    """Download one candidate ({url, source_page?, title?}). Never raises for bad input:
    returns {"url", "skipped": reason} instead."""
    url = candidate["url"]
    if _blocked(url, cfg) or _blocked(candidate.get("source_page") or "", cfg):
        return {"url": url, "skipped": "blocked domain"}
    try:
        data = _download(url, cfg)
        im, ext = _check(data, cfg)
    except (HttpError, ValueError) as e:
        return {"url": url, "skipped": str(e)}

    phash = perceptual_hash(im)
    if _is_duplicate(phash, known_hashes):
        return {"url": url, "skipped": "duplicate", "phash": phash}

    path = out_dir / f"{hashlib.sha1(data).hexdigest()[:12]}.{ext}"
    path.write_bytes(data)
    return {"url": url, "path": str(path), "width": im.size[0], "height": im.size[1], "phash": phash,
            "source_page": candidate.get("source_page"), "title": candidate.get("title")}


def fetch_many(candidates: list[dict], out_dir: Path, cfg: dict,
               exclude_hashes: set[str] = frozenset(), workers: int = 8) -> list[dict]:
    """Download candidates in parallel; skip near-duplicates of `exclude_hashes`,
    of files already in `out_dir` and of each other (first in list order wins)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    index = _load_index(out_dir)
    by_url = {v["url"]: name for name, v in index.items() if (out_dir / name).exists()}
    known = list(exclude_hashes) + [v["phash"] for v in index.values()]

    def one(c: dict) -> dict:
        name = by_url.get(c["url"])
        if name:   # downloaded in an earlier call: reuse, don't count as its own duplicate
            if any(_is_duplicate(index[name]["phash"], [h]) for h in exclude_hashes):
                return {"url": c["url"], "skipped": "duplicate", "phash": index[name]["phash"]}
            with Image.open(out_dir / name) as im:
                w, h = im.size
            return {**index[name], "path": str(out_dir / name), "width": w, "height": h, "cached": True}
        return fetch_one(c, out_dir, cfg, known)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, candidates))

    # Second pass in list order: duplicates among this batch.
    for r in results:
        if "path" not in r or r.get("cached"):
            continue
        name = Path(r["path"]).name
        if name in index or _is_duplicate(r["phash"], known):
            if name not in index:
                Path(r["path"]).unlink(missing_ok=True)
            r.pop("path")
            r["skipped"] = "duplicate"
            continue
        known.append(r["phash"])
        index[name] = {k: r.get(k) for k in ("url", "source_page", "title", "phash")}

    (out_dir / INDEX).write_text(json.dumps(index, ensure_ascii=False, indent=2))
    return results


class _ImageCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[dict] = []

    def _add(self, url: str | None, kind: str, title: str | None = None,
             width: str | None = None, height: str | None = None) -> None:
        if url and not url.startswith("data:"):
            def num(v):
                return int(v) if v and str(v).isdigit() else None
            self.found.append({"url": url.strip(), "kind": kind, "title": title,
                               "width": num(width), "height": num(height)})

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and (a.get("property") or a.get("name")) in ("og:image", "twitter:image"):
            self._add(a.get("content"), "meta")
        elif tag == "img":
            title = a.get("alt") or a.get("title")
            srcset = a.get("srcset") or a.get("data-srcset")
            if srcset:
                self._add(_largest_from_srcset(srcset), "img", title, a.get("width"), a.get("height"))
            for attr in ("data-src", "data-lazy-src", "data-original", "src"):
                if a.get(attr):
                    self._add(a[attr], "img", title, a.get("width"), a.get("height"))
                    break
        elif tag == "a" and a.get("href") and IMAGE_EXT.search(a["href"]):
            self._add(a["href"], "link", a.get("title"))


def _largest_from_srcset(srcset: str) -> str | None:
    best, best_w = None, -1.0
    for part in srcset.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        w = 0.0
        if len(bits) > 1 and bits[1][:-1].replace(".", "", 1).isdigit():
            w = float(bits[1][:-1])
        if w > best_w:
            best, best_w = bits[0], w
    return best


def _unwrap(url: str) -> str:
    """Resolve image proxies and click trackers whose query carries the real image URL,
    e.g. Next.js `/_next/image?url=...` or `t.asp?t=https://.../cow.png`."""
    parsed = urlparse(url)
    for key, values in parse_qs(parsed.query).items():
        for value in values:
            inner = urljoin(url, value)
            if (key == "url" and parsed.path.endswith("/_next/image")) or (
                    urlparse(inner).scheme in ("http", "https") and IMAGE_EXT.search(inner)):
                return inner
    return url


def extract_images(page_url: str, cfg: dict, limit: int = 40) -> list[dict]:
    """List likely content images on a page, best first: og:image, direct links to image
    files, then <img> by declared size. Icons, logos and tiny images are dropped."""
    resp = get(page_url, timeout=cfg["fetch"]["timeout_s"], user_agent=cfg["fetch"]["user_agent"])
    collector = _ImageCollector()
    collector.feed(resp.text)

    min_side = cfg["fetch"]["min_short_side_px"] // 4   # declared sizes are often thumbnails
    rank = {"meta": 0, "link": 1, "img": 2}
    seen, out = set(), []
    for item in collector.found:
        url = _unwrap(urljoin(resp.url, item["url"]))
        if url in seen or JUNK_URL.search(url) or url.lower().split("?")[0].endswith(".svg"):
            continue
        if item["width"] and item["height"] and min(item["width"], item["height"]) < min_side:
            continue
        seen.add(url)
        out.append({**item, "url": url, "source_page": page_url})

    out.sort(key=lambda i: (rank[i["kind"]], -((i["width"] or 0) * (i["height"] or 0))))
    return out[:limit]
