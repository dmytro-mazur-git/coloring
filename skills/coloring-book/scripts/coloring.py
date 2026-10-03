#!/usr/bin/env python3
"""coloring.py — toolkit CLI for the coloring-book skill.

Every command prints JSON to stdout; errors go to stderr with a non-zero exit code.
Heavy dependencies are imported lazily so `--help` works without them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from coloring_kit.config import load_config  # noqa: E402
from coloring_kit.http import HttpError  # noqa: E402

PROFILES = ["easy", "medium", "hard"]


def _out(data) -> None:
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")


def cmd_job_init(args, cfg):
    from coloring_kit.job import init_job
    from coloring_kit.models import JobSpec

    spec = JobSpec.from_dict(json.loads(Path(args.spec).read_text()))
    output_dir = Path(args.output_dir or cfg["output_dir"])
    _out(init_job(spec, output_dir, cfg["max_pages"]))


def cmd_search(args, cfg):
    from coloring_kit.models import to_dict
    from coloring_kit.search import search

    results = search(args.query, args.kind, args.limit, cfg)
    _out([to_dict(c) for c in results])


def cmd_extract_images(args, cfg):
    from coloring_kit.fetch import extract_images

    _out(extract_images(args.page_url, cfg, args.limit))


def cmd_fetch(args, cfg):
    from coloring_kit.fetch import fetch_many

    candidates = [{"url": u} for u in args.url or []]
    if args.candidates:
        candidates += json.loads(Path(args.candidates).read_text())
    if not candidates:
        sys.exit("error: give --url and/or --candidates")
    results = fetch_many(candidates[: args.limit], Path(args.out), cfg, set(args.exclude_hash or []))
    ok = [r for r in results if "path" in r]
    _out({"fetched": ok, "skipped": [r for r in results if "path" not in r]})


def cmd_analyze(args, cfg):
    from coloring_kit.analyze import analyze
    from coloring_kit.models import to_dict

    images = [Path(i) for i in args.image]
    if args.dir:
        images += sorted(p for p in Path(args.dir).iterdir()
                         if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"})
    profile = cfg["profiles"][args.profile]
    results = []
    for image in images:
        try:
            results.append({"path": str(image), **to_dict(analyze(image, profile))})
        except Exception as e:  # noqa: BLE001 - one broken file must not stop the batch
            results.append({"path": str(image), "error": str(e)})
    if args.sort:
        key = f"{args.sort}_score"
        results.sort(key=lambda r: r.get(key, -1), reverse=True)
    _out(results)


def cmd_thumb(args, cfg):
    from coloring_kit.analyze import thumbnail

    out = Path(args.out) if args.out else None
    _out({"thumb": str(thumbnail(Path(args.image), cfg["thumb_max_px"], out))})


def cmd_lineart(args, cfg):
    from coloring_kit.lineart import to_lineart

    _out(to_lineart(Path(args.image), Path(args.out), args.mode, cfg["profiles"][args.profile]))


def cmd_generate(args, cfg):
    from coloring_kit.generate import ProviderUnavailable, get_provider

    names = [args.provider] if args.provider else cfg["generate"]["providers"]
    for name in names:
        try:
            provider = get_provider(name, cfg["generate"])
        except ProviderUnavailable:
            continue
        w, h = (int(x) for x in args.size.split("x"))
        image = provider.generate(args.prompt, (w, h), n=1)[0]
        Path(args.out).write_bytes(image)
        _out({"path": args.out, "provider": name})
        return
    sys.exit("no image generation provider available (missing API keys?)")


def cmd_pdf(args, cfg):
    from coloring_kit.pdf import build_pdf

    _out({"pdf": str(build_pdf(Path(args.job), cfg))})


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="coloring.py", description=__doc__.splitlines()[0])
    p.add_argument("--config", help="extra config.yaml to merge over defaults")
    sub = p.add_subparsers(dest="command", required=True)

    job = sub.add_parser("job", help="job workspace").add_subparsers(dest="job_cmd", required=True)
    s = job.add_parser("init", help="create output/<job>/ from a JobSpec JSON")
    s.add_argument("--spec", required=True)
    s.add_argument("--output-dir")
    s.set_defaults(func=cmd_job_init)

    s = sub.add_parser("search", help="image search via configured providers")
    s.add_argument("--query", required=True)
    s.add_argument("--kind", choices=["coloring", "image"], required=True)
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("extract-images", help="list images on a web page, best first")
    s.add_argument("--page-url", required=True)
    s.add_argument("--limit", type=int, default=40)
    s.set_defaults(func=cmd_extract_images)

    s = sub.add_parser("fetch", help="download and validate images (parallel, dedup by pHash)")
    s.add_argument("--url", action="append", help="repeatable")
    s.add_argument("--candidates", help="JSON list from `search`/`extract-images` (keeps provenance)")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--out", required=True, help="target directory, e.g. <page dir>/candidates")
    s.add_argument("--exclude-hash", action="append", help="pHash to treat as duplicate; repeatable")
    s.set_defaults(func=cmd_fetch)

    s = sub.add_parser("analyze", help="pixel metrics and profile fit (JSON list)")
    s.add_argument("--image", action="append", default=[], help="repeatable")
    s.add_argument("--dir", help="analyze all images in a directory")
    s.add_argument("--sort", choices=["lineart", "convertibility"], help="sort best first")
    s.add_argument("--profile", choices=PROFILES, default="medium")
    s.set_defaults(func=cmd_analyze)

    s = sub.add_parser("thumb", help="small copy for vision review")
    s.add_argument("--image", required=True)
    s.add_argument("--out", help="default: <page dir>/thumbs/<name>.png")
    s.set_defaults(func=cmd_thumb)

    s = sub.add_parser("lineart", help="cleanup or convert to printable line art")
    s.add_argument("--image", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--mode", choices=["cleanup", "convert"], required=True)
    s.add_argument("--profile", choices=PROFILES, default="medium")
    s.set_defaults(func=cmd_lineart)

    s = sub.add_parser("generate", help="generate an image via configured providers")
    s.add_argument("--prompt", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--provider")
    s.add_argument("--size", default="1024x1536")
    s.set_defaults(func=cmd_generate)

    s = sub.add_parser("pdf", help="build the A4 PDF for a job")
    s.add_argument("--job", required=True)
    s.set_defaults(func=cmd_pdf)
    return p


def main() -> None:
    args = build_parser().parse_args()
    cfg = load_config(Path(args.config) if args.config else None)
    try:
        args.func(args, cfg)
    except NotImplementedError:
        sys.exit(f"'{args.command}' is not implemented yet (skeleton)")
    except (ValueError, FileNotFoundError, HttpError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
