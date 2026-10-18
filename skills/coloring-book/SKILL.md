---
name: coloring-book
description: Find ready-made kids' coloring pages online for a text description and print them as an A4 PDF (one or many pages). Use when the user asks for a coloring page / coloring book / розмальовка / раскраска, e.g. "розмальовка з динозавром", "5 coloring pages of farm animals for a 4-year-old".
---

# Coloring book orchestrator

You orchestrate the creation of a kids' coloring-page PDF. You plan and coordinate;
the image search happens in subagents and in the `coloring.py` toolkit.
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

## Step 2 — Search (pages in parallel)

Pages come only from ready-made coloring pages found online: nothing is generated and
no photo or clipart is converted into line art.

Run `coloring:coloring-searcher` for all pages **in parallel** (at most
`max_parallel_agents` from `config.yaml` at once). Pass each subagent: the absolute
`page.json` path(s), the absolute `skill_dir`, and the difficulty profile.

Pages of the same subject or character (`variants`, or "each girl twice") go to ONE
subagent: pass all their `page.json` paths; it searches once and picks a different picture
for each.

**Subagent prompts stay short:** the role file already holds the procedure. Pass the page
paths, `skill_dir`, profile, character name, exclusions and anything the user said about
earlier picks, and end with: "Final message: only the JSON lines from your Output section."

Subagents return a short JSON summary; details are in `page.json`. Do not open candidate
images yourself — keep your context small. (Exception: the contact sheet below.)

A page the searcher returns as `not_found` gets one more search round only if you can give
the subagent something new (other query wording, a related simpler subject the user would
accept). Otherwise it is `failed`.

**Preview mode** (`preview: true`): the subagent returns `"status": "candidates"` with a
contact sheet instead of a pick. Look at the sheet once, then show it to the user
(send the file if you can, otherwise give its path) with one line per number (site, why it
matches, likeness to the reference), recommend one, and **stop and wait** for the user's
choice. Then run `coloring.py job select --page <page.json> --n <N>` (several numbers →
several pages: give each extra pick its own page) and continue with Step 3. If the user
likes none, run the search again in preview mode, telling the subagent to exclude the
hashes of everything already shown.

**User rejects a finished page** ("не подобається", "не схожий"): treat it as a new search
for that page with `preview: true`. Keep the job; pass the rejected `final.phash` as an
exclusion and the user's reason to the subagent.

## Step 3 — Final review (by you, from one image)

Run `coloring.py review-sheet --job <job dir>`: one image with every page's final next to
its character reference, plus a metrics line per page (L = line-art score, gray, T = text,
`!fit` = outside the difficulty profile). Look at it **once** and check each page against
`reference/quality-criteria.md`; for characters compare hair / face / outfit with the REF
tile one by one (e.g. one ponytail vs two pigtails is a reject). Record each decision:
`coloring.py job verdict --page <page.json> --accept|--reject --reason "..." [--score N]`.
User-chosen pages are rejected only for hard defects (safety, text, gray fills).
Use the `coloring:quality-inspector` subagent only for books over 9 pages or when you need
a second opinion on specific pages.

For each `reject`: run the searcher once more for that page, excluding the rejected
`final.phash`. A page rejected again is `failed`.

## Step 4 — Build the PDF and report

Run `coloring.py pdf --job <job dir>`. Then tell the user, in their language:

- the PDF path,
- per page: subject and source domain,
- which pages failed and why, with a suggestion (rephrase, different or more common subject).

Failed pages never block the PDF if at least one page succeeded.

## Nothing found

When no page has an accepted image:

1. Do not build the PDF.
2. Run `coloring.py job stop --job <job dir> --reason nothing_found --pages <n,...>`.
3. Tell the user, in their language, that no suitable ready-made coloring page was found
   for these subjects (short reason from each `page.json` `search.notes`), and suggest a
   different or more common subject. Mention the job directory: candidates found so far are
   kept there.
