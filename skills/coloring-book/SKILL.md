---
name: coloring-book
description: Create printable A4 coloring pages (PDF, one or many pages) for children from a text description. Use when the user asks for a coloring page / coloring book / розмальовка / раскраска, e.g. "розмальовка з динозавром", "5 coloring pages of farm animals for a 4-year-old".
---

# Coloring book orchestrator

You orchestrate the creation of a kids' coloring-page PDF. You plan and coordinate;
the heavy image work happens in subagents and in the `coloring.py` toolkit.
Full design: `docs/architecture.md` in the plugin repo.

Paths below are relative to this skill's base directory (`SKILL_DIR`).
Toolkit: `python3 SKILL_DIR/scripts/coloring.py <command> ...` (JSON on stdout).
Subagents do not know `SKILL_DIR`: always pass it to them as an absolute `skill_dir`.

## Step 0 — Safety gate

The audience is children. If the request is not appropriate for kids (violence, horror,
sexual content, hateful symbols, real-person likeness used inappropriately), refuse or
offer a kid-friendly alternative. Do not continue with an unsafe subject.

## Step 1 — Plan the job

Extract a JobSpec from the user's message (schema: `reference/page-schema.md`):

- `language` — the user's language (captions use it).
- `mode` — `variants` (N pictures of the same subject) or `set` (a theme split into
  N concrete, easily recognizable subjects you choose).
- `difficulty` — `easy` (3–5 y), `medium` (6–8 y, default), `hard` (9–12 y);
  see `reference/difficulty-profiles.md`. Infer from age if given.
- page count — default 1, maximum 10.
- `captions` (default: off, on for `set`), `cover` (default: on for `set` with ≥ 3 pages),
  `orientation` (`auto` unless the user asks).
- per page: English `subject` and optional `query_hints`; `caption` in the user's language.

Ask the user only if the subject itself is unclear. Otherwise proceed with defaults.

Write the spec to a temp file and run `coloring.py job init --spec <file>`.
It prints the job directory and the per-page `page.json` paths.

## Step 2 — Source cascade (stage by stage, pages in parallel)

Run each stage for all still-open pages **in parallel** (one subagent per page, at most
`max_parallel_agents` from `config.yaml` at once). Pass each subagent: the absolute
`page.json` path, the absolute `skill_dir`, and the difficulty profile.

1. `coloring:coloring-searcher` — ready-made coloring pages.
2. `coloring:image-scout` — for pages still `not_found`: images that convert well to line art.
3. `coloring:illustrator` — for pages still open: generate with an external API.

For `variants` mode you may give stage 1 a single subagent for all pages of the same
subject (one search, N distinct picks).

Subagents return a short JSON summary; details are in `page.json`. Do not open candidate
images yourself — keep your context small.

## Step 3 — Final inspection

Run one `coloring:quality-inspector` over all pages with `final.png` (pass the absolute
job directory and `skill_dir`).
For each `reject`: send the page to the next stage of the cascade once
(stage 1 → 2 → 3). A rejected stage-3 page gets one more illustrator attempt, then `failed`.

## Step 4 — Build the PDF and report

Run `coloring.py pdf --job <job dir>`. Then tell the user, in their language:

- the PDF path,
- per page: subject and origin (found / converted / generated, with source domain),
- which pages failed and why, with a suggestion (rephrase, different subject).

Failed pages never block the PDF if at least one page succeeded.
