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
- per page `character`: set it when the subject is a specific known character (film,
  cartoon, series, game, book), with the franchise, e.g. "Baby from Saja Boys
  (KPop Demon Hunters)". Use the character's canonical name even if the user misspells it
  or uses a nickname/translation (e.g. "Малюк" → Baby, "Saga boys" → Saja Boys).
  Subagents then check likeness against an official reference image.
- `preview` (default false): true when the user asks to see options first
  ("спочатку покажи", "покажи варіанти", "let me choose"), or when they rejected a pick and
  want a new search. See `reference/characters-and-preview.md`.

Ask the user only if the subject itself is unclear. Otherwise proceed with defaults.

Write the spec to a temp file and run `coloring.py job init --spec <file>`.
It prints the job directory and the per-page `page.json` paths.

Also run `coloring.py config get generate.enabled` once: it decides whether stage 3 exists.

## Step 2 — Source cascade (stage by stage, pages in parallel)

Run each stage for all still-open pages **in parallel** (one subagent per page, at most
`max_parallel_agents` from `config.yaml` at once). Pass each subagent: the absolute
`page.json` path, the absolute `skill_dir`, and the difficulty profile.

1. `coloring:coloring-searcher` — ready-made coloring pages.
2. `coloring:image-scout` — for pages still `not_found`: images that convert well to line art.
3. `coloring:illustrator` — for pages still open: generate with an external API.
   **Only if `generate.enabled` is true.** Otherwise go to "Stopping" below as soon as
   stage 2 leaves any page open.

For `variants` mode you may give stage 1 a single subagent for all pages of the same
subject (one search, N distinct picks).

Subagents return a short JSON summary; details are in `page.json`. Do not open candidate
images yourself — keep your context small. (Exception: the contact sheet below.)

**Preview mode** (`preview: true`): a stage subagent returns `"status": "candidates"` with a
contact sheet instead of a pick. Look at the sheet once, then show it to the user
(send the file if you can, otherwise give its path) with one line per number (site, why it
matches, likeness to the reference), recommend one, and **stop and wait** for the user's
choice. Then run `coloring.py job select --page <page.json> --n <N>` (several numbers →
several pages: give each extra pick its own page) and continue with Step 3. If the user
likes none, run the stage again in preview mode, telling the subagent to exclude the hashes
of everything already shown; if stage 1 is exhausted, go on to stage 2.

**User rejects a finished page** ("не подобається", "не схожий"): treat it as a new search
for that page with `preview: true`. Keep the job; pass the rejected `final.phash` as an
exclusion and the user's reason to the subagent.

## Step 3 — Final inspection

Run one `coloring:quality-inspector` over all pages with `final.png` (pass the absolute
job directory and `skill_dir`).
For each `reject`: send the page to the next stage of the cascade once
(stage 1 → 2 → 3). A rejected stage-3 page gets one more illustrator attempt, then `failed`.
With generation disabled, a rejected page whose next stage would be 3 means "Stopping".

## Step 4 — Build the PDF and report

Run `coloring.py pdf --job <job dir>`. Then tell the user, in their language:

- the PDF path,
- per page: subject and origin (found / converted / generated, with source domain),
- which pages failed and why, with a suggestion (rephrase, different subject).

Failed pages never block the PDF if at least one page succeeded.

## Stopping (generation needed but disabled)

When a page can only be completed by generation and `generate.enabled` is false:

1. Do not start any further subagents and do not build the PDF.
2. Run `coloring.py job stop --job <job dir> --reason generation_disabled --pages <n,...>`
   listing every page still without an accepted image.
3. Tell the user, in their language: the job was stopped because these pages
   (subject, short reason from `page.json` stage notes) had no suitable ready-made or
   convertible image and generation is turned off. Suggest a different or more common
   subject, or enabling generation later. Mention the job directory: candidates found so
   far are kept there.
