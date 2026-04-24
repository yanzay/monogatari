# Authoring helpers

Five small CLIs that make curriculum maintenance practical. All read/write
the canonical source-of-truth files (`pipeline/inputs/story_*.bilingual.json`,
`data/vocab_state.json`, `data/grammar_state.json`); none of them invent
business logic — they expose the existing pipeline more directly.

| Tool | Purpose |
|---|---|
| `vocab.py`   | Search / inspect the vocab inventory; dry-run sentences for mints |
| `cadence.py` | Probe pedagogical cadence rules (R1/R2/G1/G2) without the pytest skipif dance |
| `spec.py`    | Surgical edits to bilingual specs (append/replace/delete/move/find) |
| `weave.py`   | Generate, preview, and apply reinforcement-weave plans |
| `regen.py`   | Regenerate / validate / diff stories |

All commands read from the workspace root and require the project venv
(`.venv/bin/python pipeline/tools/<name>.py …`).

## `vocab.py` — vocabulary inventory

```bash
vocab.py search 思                    # all words containing 思
vocab.py info W00043                  # full record + every story occurrence
vocab.py orphans --max 1              # words used in ≤1 stories
vocab.py first-occurrence W00150      # which story first uses W00150
vocab.py would-mint "毎日、本を読みます。"  # tokenize + flag any new mints
vocab.py range W00200 W00240          # numeric range view
```

`would-mint` is the killer feature: write any candidate sentence and find
out **before** committing it whether it would mint a new word.

## `cadence.py` — pedagogical-cadence probe

```bash
cadence.py vocab-reinforce            # Rule R1: ≥2 reuses in next 10 stories
cadence.py vocab-reinforce --story 12 # only intros from story 12
cadence.py vocab-abandoned            # Rule R2: RETIRED 2026-04-24 (no-op stub)
cadence.py grammar-reinforce          # Rule G2: introduced grammar reused
cadence.py validate                   # validate.py over the full library
cadence.py all                        # everything, in one report
```

Skips the `PEDAGOGICAL_CADENCE_ENABLED` flag dance — always runs the rule
checks live, regardless of how the test file is configured.

## `spec.py` — surgical bilingual editor

```bash
spec.py show 18                              # pretty-print spec
spec.py append 18 --jp "..." --en "..."      # append a sentence
spec.py replace 18:5 --jp "..." --en "..."   # replace sentence index 5
spec.py delete 18:5                          # delete sentence index 5
spec.py move 18:5 --to 18:8                  # reorder within a story
spec.py find "鞄"                             # all stories containing 鞄
spec.py title 18 --jp "..." --en "..."       # change a title
```

Avoids the find-and-replace English-text drift problem (where the EN
text changes between author iterations and string-based replacement
silently fails).

## `weave.py` — reinforcement-weave assistant

```bash
weave.py suggest > plan.json     # auto-draft a plan: one stub per R1 violation
# (edit plan.json by hand: fill in JP + EN, choose target, etc.)
weave.py preview plan.json       # tokenize each weave; flag any mints
weave.py apply plan.json --regen # apply, regen library, validate
```

Plan format (JSON):

```json
[
  {"story": 18, "jp": "犬は早いです。", "en": "The dog is fast."},
  {"story": 19, "replace": 5, "jp": "...", "en": "..."},
  {"story": 20, "jp": "# TODO: weave 椅子", "en": "TODO"}
]
```

Lines whose JP starts with `#` are treated as comments and skipped.

## `regen.py` — story regeneration

```bash
regen.py story 18              # SAFE: full library regen (preserves first-occurrence)
regen.py story 18 --unsafe     # FAST: regen one story only; may corrupt is_new flags
regen.py all                   # equivalent to pipeline/regenerate_all_stories.py --apply
regen.py validate              # validate every shipped story
regen.py diff 18               # show what regenerating one story would change
```

The library-wide first-occurrence pass means **single-story regen is
unsafe by default** — adding a word to story_18 can shift the
`is_new=true` flag from story_24 (its previous first appearance) to
story_18 across multiple stories. `--unsafe` skips that pass when you
just want to confirm token shape.
