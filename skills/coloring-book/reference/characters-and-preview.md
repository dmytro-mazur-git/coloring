# Known characters and candidate preview

## Known characters: reference image and likeness

A page has a `character` field (in `page.json`) when the subject is a specific known
character from a film, cartoon, series, game or book (e.g. "Baby from Saja Boys
(KPop Demon Hunters)"). Fan-made coloring pages are often off-model, and a source title
saying "Baby" does not make the drawing look like Baby. So, before judging candidates:

1. **Get a reference.** Use WebSearch/WebFetch to find an official image of the character
   alone: the franchise's fandom wiki page, the studio/streamer site, official posters
   or character art. Prefer a clear, front-ish full or half-body image.
   Download it with `coloring.py fetch --url <img> --out <page dir>/ref`
   (if it is rejected as too small, a reference may be small: save it with a short Python
   `requests` call instead). Copy/rename it to `<page dir>/ref/ref.png` (any format PIL
   reads is fine) and set `"reference": "ref/ref.png"` in `page.json`.
2. **Write what identifies the character** into `<page dir>/ref/notes.md`: 2–4 lines on
   hair (style, fringe), face/eyes/expression, signature outfit and accessories.
   If the character has several official looks (stage costume, casual), note the main ones.
3. **Check every candidate against the reference.** Look at the reference and the
   candidate thumbnails together (Read both). Rate likeness: `high` (hair, face and
   signature outfit/accessories all match), `medium` (recognizable but off in one of them),
   `low` (generic face or wrong look; only the label says it is the character).
   - Never accept `low`. Prefer `high`; use `medium` only if nothing better exists, and say so.
   - Being labelled as the character by the source is required too (title, file name,
     alt text or caption): record which in `why`.
   - Reject candidates showing other characters when the user asked for this one alone.

## Preview mode

When `page.json` has `"preview": true`, the user wants to see candidates and choose.
The stage subagent then **does not pick and does not write `final.png`**. Instead it:

1. Gathers and filters candidates as usual (labelled, line art or convertible, safe,
   likeness ≥ medium for characters). For stage 2, the candidate to show is the
   **converted** result (`conv_N.png`), with `"mode": "ready"`.
2. Keeps the best **2–6**, ordered best first, and writes `<page dir>/candidates.json`:
   ```json
   {"stage": "stage1", "reference": "ref/ref.png",
    "candidates": [{"n": 1, "path": "candidates/abc.png", "mode": "cleanup",
                    "source_url": "...", "source_page": "...",
                    "why": "file baby.png, alt 'coloring page of Baby'",
                    "likeness": "high", "note": "bust portrait, clean, no watermark"}]}
   ```
   `reference` is null when the page has no character. Paths are relative to the page dir.
3. Builds the sheet: `coloring.py sheet --page <page.json>` (REF tile + numbers 1..N).
4. Sets `stages.<stage>.status` to `"candidates"` and returns
   `{"page": n, "status": "candidates", "sheet": "<abs path>", "count": N, "note": "..."}`
   plus one line per candidate: `N — site — why — likeness — note`.

The orchestrator shows the sheet to the user, waits for their choice, then runs
`coloring.py job select --page <page.json> --n <N>`, which cleans the chosen image up into
`final.png` (keeping any earlier final as `previous_final_K.png`) and records the choice.
If the user likes none, the next round searches again, excluding hashes of everything
already shown (`analyze` gives `phash`).
