# Authoring helpers

Small CLIs that make curriculum maintenance practical. All read/write the canonical source-of-truth files (`pipeline/inputs/story_*.bilingual.json`, `data/vocab_state.json`, `data/grammar_state.json`). None invent business logic — they expose the existing pipeline more directly.

All commands require the project venv and must be invoked from the project root:

```bash
source .venv/bin/activate
python3 pipeline/tools/<name>.py …
```

| Tool | Purpose |
|------|---------|
| `agent_brief.py` | Compose the full JSON context the agent reads before drafting a story |
| `cadence.py` | Probe pedagogical cadence rules (R1/G1/G2) live, without the pytest flag dance |
| `cleanup_audio_orphans.py` | Delete orphan word/sentence audio files left by re-shipping |
| `cleanup_state_backups.py` | Prune `state_backups/` per a retention policy (keep last N + ≤D days) |
| `forbid.py` | Check sentences / list active banned patterns |
| `palette.py` | Browse available vocabulary by sensory category for a given story |
| `regen.py` | Regenerate / validate / diff stories |
| `spec.py` | Surgical edits to bilingual specs (append / replace / delete / move / find) |
| `story.py` | Inspect shipped story JSON |
| `vocab.py` | Search / inspect the vocab inventory; dry-run sentences for mints |
| `weave.py` | Generate, preview, and apply reinforcement-weave plans |

**Back-compat no-ops (kept for scripting stability; do nothing meaningful):**
- `reconcile_grammar_intros.py` — grammar attributions are now derived on-read (Phase A, 2026-05-01); no drift to reconcile.
- `backfill_grammar_intros.py` — same reason; retired.
- `rename_gids.py` — legacy G###_slug → catalog-form id migration; already complete.

---

## `agent_brief.py` — story context for the authoring agent

Called by `author_loop.py author N --brief-only`. Can also be invoked directly:

```bash
python3 pipeline/tools/agent_brief.py N
python3 pipeline/tools/agent_brief.py N --json   # machine-readable
```

Returns a JSON payload with: per-story ladder, seed-plan must-mints, mint budget, grammar debt, reinforcement debts, available palette, forbidden zones, coverage gaps, echo warnings, and previous 3 story summaries. This is the agent's entire memory before drafting.

---

## `vocab.py` — vocabulary inventory

```bash
vocab.py search 思                         # all words containing 思
vocab.py info W00043                       # full record + every story occurrence
vocab.py would-mint "毎日、本を読みます。"   # tokenize + flag any new mints
vocab.py orphans --max 1                   # words used in ≤1 stories
vocab.py first-occurrence W00043           # which story first uses W00043
vocab.py range W00080 W00098               # numeric range view
```

**`would-mint` is the key preflight.** Write any candidate sentence and see exactly which new vocabulary it would introduce before committing it to a spec.

---

## `palette.py` — word inventory by sensory category

```bash
palette.py N              # available words for story N, by category
palette.py N --format json
```

Groups the available vocabulary into sensory/semantic buckets (spatial, action, colour, weather, etc.) so the agent can see what the corpus can currently express rather than guessing.

---

## `cadence.py` — pedagogical cadence probe

```bash
cadence.py vocab-reinforce              # Rule R1: words whose window is closing
cadence.py vocab-reinforce --story 12   # only intros from story 12
cadence.py grammar-reinforce            # Rule G2: introduced grammar reused?
cadence.py validate                     # validate.py over the full library
cadence.py all                          # everything in one report
```

Skips the `PEDAGOGICAL_CADENCE_ENABLED` flag dance — always runs the rule checks live, regardless of how the test file is configured.

---

## `forbid.py` — banned-pattern checker

```bash
forbid.py check "猫は静かです。"   # check a sentence for banned patterns
forbid.py list                     # show all active bans with rationale
```

Reads `pipeline/forbidden_patterns.json`. Bans are patterns that have produced repeated literary defects (closer noun-piles, tautological equivalence, etc.) and should never be used again.

---

## `spec.py` — surgical bilingual editor

```bash
spec.py show 11                              # pretty-print spec
spec.py append 11 --jp "…" --en "…"         # append a sentence
spec.py replace 11:3 --jp "…" --en "…"      # replace sentence index 3
spec.py delete 11:3                          # delete sentence index 3
spec.py move 11:3 --to 11:5                  # reorder within a story
spec.py find "鞄"                             # all stories containing 鞄
spec.py title 11 --jp "…" --en "…"          # change title
```

Avoids the find-and-replace English-text drift problem (where EN text changes between iterations and string-based replacement silently fails).

---

## `weave.py` — reinforcement-weave assistant

```bash
weave.py suggest > plan.json      # auto-draft a plan: one stub per R1 violation
# (edit plan.json: fill in JP + EN, choose target story, etc.)
weave.py preview plan.json        # tokenize each weave; flag any mints
weave.py apply plan.json --regen  # apply, regen library, validate
```

Plan format:

```json
[
  {"story": 12, "jp": "犬は早いです。",  "en": "The dog is fast."},
  {"story": 13, "replace": 3, "jp": "…", "en": "…"},
  {"story": 14, "jp": "# TODO: weave 椅子", "en": "TODO"}
]
```

Lines whose `jp` starts with `#` are treated as comments and skipped.

---

## `regen.py` — story regeneration

```bash
regen.py story 11              # SAFE: full library regen (preserves first-occurrence)
regen.py story 11 --unsafe     # FAST: regen one story; may corrupt is_new flags
regen.py all                   # equivalent to regenerate_all_stories.py --apply
regen.py validate              # validate every shipped story
regen.py diff 11               # show what regenerating one story would change
```

**Single-story regen is unsafe by default.** Adding a word to story 11 can shift `is_new=true` from story 18 to story 11 across multiple stories. Use `--unsafe` only when you just want to confirm token shape, not update the library.

---

## `cleanup_state_backups.py` — backup-garden retention

```bash
cleanup_state_backups.py                               # dry-run, top-level
cleanup_state_backups.py --all-subdirs                 # include sub-dirs
cleanup_state_backups.py --keep 3 --days 3 --apply    # aggressive prune
cleanup_state_backups.py --subdir regenerate_all_stories --apply
```

Default policy: keep the **N most-recent** files **per stem** (`vocab_state` and `grammar_state` counted separately) plus everything **newer than D days**. Defaults: `--keep 5 --days 7`. Without `--apply` it prints a plan but deletes nothing.

---

## `cleanup_audio_orphans.py` — stale audio removal

```bash
cleanup_audio_orphans.py        # dry-run
cleanup_audio_orphans.py --apply
```

Detects three kinds of orphan:

1. `audio/words/W*.mp3` whose WID is no longer in `vocab_state.json` (left by ID-changing re-ships).
2. `audio/story_N/sX.mp3` where sentence index X exceeds the current sentence count (left by sentence-count-shrinking re-ships).
3. Legacy `audio/story_N/w_W*.mp3` per-story word audio (migrated to flat `audio/words/` layout on 2026-04-29).

Run after any re-ship that changes word IDs or sentence counts, before the final `pytest pipeline/tests/ -q`.
