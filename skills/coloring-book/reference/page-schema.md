# Job and page schema

## JobSpec (input of `coloring.py job init --spec`)

```json
{
  "request": "original user text",
  "language": "uk",
  "mode": "variants | set",
  "difficulty": "easy | medium | hard",
  "captions": false,
  "cover": false,
  "orientation": "auto | portrait | landscape",
  "title": "Тварини ферми",
  "pages": [
    {"n": 1, "subject": "cow", "caption": "Корова", "query_hints": ["cartoon cow"]}
  ]
}
```

## page.json (one per page, `pages/NN/page.json`)

```json
{
  "n": 1,
  "subject": "cow",
  "caption": "Корова",
  "difficulty": "easy",
  "query_hints": [],
  "exclude_hashes": [],
  "status": "planned | selected | accepted | rejected | failed",
  "stages": {
    "stage1": {"status": "found | not_found", "queries": [], "checked": 0, "candidate": null, "score": null, "notes": ""},
    "stage2": {"...": "same shape"},
    "stage3": {"status": "done | failed", "prompts": [], "attempts": 0, "score": null, "notes": ""}
  },
  "final": {
    "path": "final.png",
    "origin": "found | converted | generated",
    "source_url": null,
    "source_page": null,
    "provider": null,
    "prompt": null,
    "phash": null
  },
  "inspection": {"verdict": "accept | reject", "score": 0, "reasons": []}
}
```

Ownership: a stage subagent writes only its own `pages/NN/` directory. Only the
orchestrator (via `coloring.py`) writes `job.json`.
