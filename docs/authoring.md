# Monogatari — Authoring Guide

How to generate new stories using the Rovo Dev pipeline.

**Version 0.1** · Pipeline implemented at M4

---

## Overview

Stories are authored collaboratively: the pipeline scripts prepare structured prompts, and Rovo Dev (the AI coding assistant) executes them directly — no external LLM API keys required.

```
pipeline/run.py --step 1   →  generates planner_prompt.md
                              [Rovo Dev writes plan.json]
pipeline/run.py --step 2   →  validates plan, generates writer_prompt.md
                              [Rovo Dev writes story_raw.json]
pipeline/run.py --step 3   →  validates story_raw.json (deterministic)
pipeline/run.py --step 4   →  ships story, updates state
```

---

## Prerequisites

```
data/vocab_state.json     — current learner vocabulary
data/grammar_state.json   — current grammar points
pipeline/authoring_rules.md — writer style guide (given to Rovo Dev)
```

---

## Step-by-step workflow

### Step 1 — Generate the planner prompt

```bash
python3 pipeline/run.py --step 1 \
    --n-new-words 3 \
    --n-new-grammar 1 \
    --theme "rainy library"
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--n-new-words` | `3` | How many new words to introduce |
| `--n-new-grammar` | `1` | Max new grammar points (0 = consolidation story) |
| `--theme` | none | Optional theme hint for the planner |
| `--vocab` | `data/vocab_state.json` | Path to vocab state |
| `--grammar` | `data/grammar_state.json` | Path to grammar state |

This writes `pipeline/planner_prompt.md`.

**Then ask Rovo Dev:**
> "Execute the planner prompt in `pipeline/planner_prompt.md` and write `pipeline/plan.json`"

Rovo Dev will:
- Select 3 new words appropriate for i+1 difficulty
- Choose which existing weak words to reinforce
- Optionally select a new grammar point
- Write `pipeline/plan.json`

**Review `pipeline/plan.json` before proceeding.** You can edit it by hand — change the theme, swap a word, adjust the target count, etc.

---

### Step 2 — Generate the writer prompt

```bash
python3 pipeline/run.py --step 2
```

This:
1. Validates `pipeline/plan.json` (checks new_words not in vocab, prereqs satisfied)
2. Generates `pipeline/writer_prompt.md` with the full allowed word/grammar lists and authoring rules

**Then ask Rovo Dev:**
> "Execute the writer prompt in `pipeline/writer_prompt.md` and write `pipeline/story_raw.json`"

Rovo Dev will author the story following `pipeline/authoring_rules.md`:
- Sentences flow inline, 5–8 total
- Each new word appears at least twice
- New grammar appears at least 3 times
- Every token has `word_id` or `grammar_id`
- Kanji tokens have `r` (kana reading)
- Inflected forms have an `inflection` block

---

### Step 3 — Validate

```bash
python3 pipeline/run.py --step 3
```

Runs `pipeline/validate.py` — 10 deterministic checks:

| # | Check |
|---|-------|
| 1 | Schema validity |
| 2 | Closed vocabulary (all word_ids known) |
| 3 | Closed grammar (all grammar_ids known) |
| 4 | Budget (exactly planned new words, all used) |
| 5 | Surface ↔ ID consistency + inflection correctness |
| 6 | Reuse quota (≥ 60% of content tokens have occ < 5) |
| 7 | Length (5–8 sentences, within target token count) |
| 8 | No forbidden topics in gloss_en |
| 9 | Gloss sanity (non-empty, plausible length ratio) |
| 10 | Round-trip (no double spaces, no stray ASCII, terminal punct) |

If validation **fails**, ask Rovo Dev to fix `pipeline/story_raw.json` based on the error messages, then retry step 3.

---

### Step 4 — Ship

```bash
python3 pipeline/run.py --step 4
```

This:
1. Runs a final validation pass
2. Backs up current `vocab_state.json` and `grammar_state.json` to `state_backups/`
3. Adds new words to `vocab_state.json`
4. Increments occurrence counts for all words used
5. Adds new grammar points to `grammar_state.json`
6. Copies the story to `stories/story_N.json`

Reload `http://localhost:8000` and click "Next →" to read the new story.

---

## Direct script usage

You can also run each stage individually:

```bash
# Stage 1 — generate planner prompt only
python3 pipeline/planner.py --n-new-words 3 --theme "café morning"

# Validate a plan
python3 pipeline/planner.py --validate pipeline/plan.json

# Stage 2 — generate writer prompt from existing plan
python3 pipeline/writer.py --plan pipeline/plan.json

# Stage 3 — validate a story (with or without plan)
python3 pipeline/validate.py pipeline/story_raw.json
python3 pipeline/validate.py pipeline/story_raw.json --plan pipeline/plan.json

# Stage 3 — JSON output (useful for scripting)
python3 pipeline/validate.py pipeline/story_raw.json --json

# Stage 5 — update state only (dry run)
python3 pipeline/state_updater.py pipeline/story_raw.json --dry-run

# Stage 5 — ship with plan (fills in new word definitions)
python3 pipeline/state_updater.py pipeline/story_raw.json --plan pipeline/plan.json

# Run validator tests
python3 pipeline/test_validate.py
```

---

## Editing plan.json by hand

After step 1, you can freely edit `pipeline/plan.json` before step 2. Common edits:

- **Change theme/setting** — rewrite `theme` and `setting` fields
- **Swap a word** — change a `word_id` in `new_words` and update `new_word_definitions`
- **Remove new grammar** — set `new_grammar` to `[]`
- **Adjust target** — change `target_word_count` (validator allows ±30%)
- **Add reuse constraints** — add word_ids to `constraints.must_reuse_words`

Run `python3 pipeline/planner.py --validate pipeline/plan.json` after any edit.

---

## Difficulty policy

| Parameter | Value |
|-----------|-------|
| New words per story | 3 (default), adjust with `--n-new-words` |
| New grammar per story | 0 or 1 |
| Sentence count | 5–8 |
| Content token target | 28–65 (varies by story) |
| Reuse quota | ≥ 60% of content tokens must have `occurrences < 5` |
| New word repetition | Each new word must appear ≥ 2× |
| New grammar repetition | New grammar must appear ≥ 3× |

---

## State management

### Backups

Every `pipeline/run.py --step 4` creates timestamped backups:
```
state_backups/vocab_state_20260421_193122.json
state_backups/grammar_state_20260421_193122.json
```

To roll back: copy the backup files back to `data/`.

### Intermediate files

| File | Purpose | Safe to delete? |
|------|---------|-----------------|
| `pipeline/planner_prompt.md` | Input to Rovo Dev for planning | Yes (regenerated each run) |
| `pipeline/writer_prompt.md` | Input to Rovo Dev for writing | Yes (regenerated each run) |
| `pipeline/plan.json` | Ephemeral plan for current story | After step 4 |
| `pipeline/story_raw.json` | Raw story before shipping | After step 4 |

---

## File structure

```
monogatari/
├── data/
│   ├── vocab_state.json       — learner vocabulary (updated after each story)
│   └── grammar_state.json     — grammar points (updated after each story)
├── docs/
│   ├── spec.md                — system specification
│   └── authoring.md           — this document
├── pipeline/
│   ├── authoring_rules.md     — writer style guide (given to Rovo Dev)
│   ├── planner.py             — Stage 1: generates planner prompt
│   ├── writer.py              — Stage 2: generates writer prompt
│   ├── validate.py            — Stage 3: deterministic validator (10 checks)
│   ├── state_updater.py       — Stage 5: updates vocab/grammar state
│   ├── run.py                 — orchestrator (steps 1–4)
│   └── test_validate.py       — validator test suite (38 tests)
├── state_backups/             — timestamped state backups
├── stories/
│   ├── story_1.json           — Rain (手-authored)
│   └── story_2.json           — The Evening Park (pipeline-authored)
├── css/style.css
├── js/app.js
└── index.html
```

---

## Adding grammar to grammar_state.json manually

When `state_updater.py` adds a new grammar point (from `plan.new_grammar_definitions`),
it fills in all fields automatically. If you need to add one manually:

```json
{
  "id": "G010_to_quote",
  "title": "と — quotation marker",
  "short": "Marks a quoted phrase or thought.",
  "long": "The particle と after a phrase marks it as a direct or indirect quote...",
  "genki_ref": "L9",
  "first_story": 3,
  "prerequisites": ["G003_desu"]
}
```

Add it to `grammar_state.json → points` and include `G010_to_quote` in `plan.new_grammar`.

---

## Troubleshooting

**`Check 2: word_id not in vocab or plan`**
→ The writer used a word not in the allowed set. Ask Rovo Dev to replace it with an allowed word_id, or add it to `plan.new_word_definitions` and `plan.new_words`.

**`Check 4: Words in all_words_used but not found in tokens`**
→ `all_words_used` lists a word_id that doesn't appear in any token. Remove it from the list.

**`Check 5: Inflection mismatch`**
→ The `inflection.base` + `inflection.form` doesn't produce the surface `t`. Check the inflection table in `authoring_rules.md` Section 5.

**`Check 7: Content token count outside range`**
→ Story is too short or too long. Either expand the story or adjust `plan.target_word_count` to match.

**`Check 3: grammar_id not in grammar_state or plan`**
→ A particle or aux uses a grammar_id not yet defined. Add it to `plan.new_grammar` and `plan.new_grammar_definitions`, or use an already-known grammar_id.
