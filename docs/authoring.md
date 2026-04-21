# Monogatari — Authoring Guide

How to generate new stories using the Rovo Dev pipeline.

**Version 0.1** · Pipeline implemented at M4

---

## Overview

Stories are authored by **Rovo Dev** (the AI coding agent in the active conversation). The pipeline scripts prepare structured prompts and validators; Rovo Dev produces the JSON files. No external LLM API keys are required, and no third-party model is ever called.

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

---

## Authoring tooling (new in v0.2)

Three small CLI helpers were added after authoring stories 5 and 6 to remove
the most common sources of friction. They are all standalone Python scripts
with no extra dependencies — `python3 path/to/tool.py --help` lists options.

### `pipeline/lookup.py` — fast vocab + grammar search

Avoid the "is 朝 W00015 or W00016?" stall.

```bash
python3 pipeline/lookup.py 朝          # search by surface
python3 pipeline/lookup.py morning     # search by English meaning
python3 pipeline/lookup.py asa         # search by romaji
python3 pipeline/lookup.py W00015      # dump full record
python3 pipeline/lookup.py G002_ga_subject

python3 pipeline/lookup.py --next            # next free word_id, grammar_id, story_id
python3 pipeline/lookup.py --grammar-usage   # ascending — surfaces underused grammar
python3 pipeline/lookup.py --low-occ         # words with occurrences<5 (engagement reuse pool)
```

The `--grammar-usage` view is especially useful for the **"give underused grammar
real work"** authoring move (see Engagement & voice section in
`pipeline/authoring_rules.md`). Story 6 used it to elevate `G002_ga_subject`
from "registered, barely used" to "doing the central semantic move."

### `pipeline/scaffold.py` — generate `plan.json` and `story_raw.json` skeletons

Eliminates the field-name-drift class of mistakes (kana vs reading, meaning_en
vs meanings, constraints as list vs dict, etc.).

```bash
# Stage 1 — fresh plan with all required fields, ids pre-filled
python3 pipeline/scaffold.py plan \
    --title-jp 猫 --title-en "The Cat" \
    --new-words 2 --new-grammar 0

# Stage 2 — story_raw skeleton aligned with the current plan.json
python3 pipeline/scaffold.py story --sentences 7
```

The plan skeleton auto-populates `must_reuse_words` with the 5 lowest-occurrence
words from vocab, which is the engagement reuse pool. The story skeleton seeds
`new_words` and `new_grammar` from the plan so they cannot drift out of sync.

### `pipeline/precheck.py` — fast pre-flight before the full validator

Catches the cheap mistakes (idx, all_words_used, is_new placement, gloss-length
ratio) and can auto-fix many of them.

```bash
python3 pipeline/precheck.py            # report only
python3 pipeline/precheck.py --fix      # auto-fix and write back (keeps a .bak)
```

Auto-fix handles:
- missing `idx` on sentences,
- stale or wrong-order `all_words_used`,
- missing `is_new: true` on first sentence-token of a new word,
- stray `is_new: true` on a title/subtitle token,
- missing top-level `new_words` / `new_grammar` arrays.

What it cannot auto-fix (must report):
- gloss out of `[0.8, 3.0]` ratio — needs human edit,
- unknown word_ids or grammar_ids — needs author intervention.

A typical authoring loop becomes:
```bash
python3 pipeline/scaffold.py plan ...        # stage 1 skeleton
# ...fill in plan...
python3 pipeline/run.py --step 2             # validate plan
python3 pipeline/scaffold.py story --sentences 7
# ...fill in tokens + glosses...
python3 pipeline/precheck.py --fix           # cheap fixes + report
python3 pipeline/run.py --step 3             # full validate
python3 pipeline/engagement_review.py --mode print
# ...fill review.json...
python3 pipeline/engagement_review.py --mode finalize
python3 pipeline/run.py --step 4 --tts-backend google --tts-encoding MP3
```

---

## Gotchas (compiled from real authoring sessions)

### G1. Plan schema field names — no synonyms

| ✗ Wrong            | ✓ Correct      |
|--------------------|----------------|
| `kana` (in plan)   | `kana` ← fine, but you also need `reading` |
| `meaning_en`       | `meanings` (array) |
| `verb_class: ichidan` | `verb_class: "ichidan"` (string, may be `null`) |
| `constraints: [...]` | `constraints: { must_reuse_words, forbidden_words, avoid_topics }` (object) |
| `new_grammar` lists already-shipped points | Only list grammar that is NOT already in `data/grammar_state.json` |

The scaffold tool enforces the canonical names. Use it.

### G2. `is_new` belongs on the first **sentence**-token

Title/subtitle tokens **do not** count as the first occurrence for the
`is_new` flag. Even if the title introduces the word visually, the validator
requires the first occurrence inside `sentences[]` to carry `is_new: true`.

```jsonc
// ✗ wrong — fails Check 4
"title":   { "tokens": [{ "t": "猫", "word_id": "W00028", "is_new": true }] },
"sentences": [
    { "idx": 0, "tokens": [{ "t": "猫", "word_id": "W00028" }] }
]

// ✓ correct
"title":   { "tokens": [{ "t": "猫", "word_id": "W00028" }] },
"sentences": [
    { "idx": 0, "tokens": [{ "t": "猫", "word_id": "W00028", "is_new": true }] }
]
```

`precheck.py --fix` will move it for you.

### G3. `all_words_used` is in **first-seen order across title→subtitle→sentences**

Not alphabetical. Not by id. Not the order of `new_words`. The exact
order in which each `word_id` is first encountered across the whole
serialized story.

The engagement quota and reuse rules are downstream of this order, so
recompute it whenever you edit tokens. `precheck.py --fix` does this for
you and preserves the canonical order.

### G4. Glosses must satisfy `0.8 ≤ EN_words / JP_tokens ≤ 3.0`

Punct tokens don't count toward JP. A 7-token sentence needs **6–21**
English words. Examples:

```
JP tokens=7  →  6 ≤ EN ≤ 21
JP tokens=8  →  7 ≤ EN ≤ 24
JP tokens=5  →  4 ≤ EN ≤ 15
```

If you write `"I look outside."` (3 words) for a 7-token sentence,
the validator will flag it. Either expand the gloss or tighten the JP.

### G5. Verb forms need `inflection`

`見ます`, `濡れて`, `食べた` etc. are not dictionary surfaces. The validator
checks the surface against `inflection.base + inflection.form`.

```jsonc
// for 見ます (polite_nonpast of 見る, ichidan)
{
  "t": "見ます",
  "r": "みます",
  "role": "content",
  "word_id": "W00006",
  "inflection": {
    "base": "見る",
    "base_r": "みる",
    "form": "polite_nonpast",
    "word_id": "W00006"
  }
}

// for 濡れて (te-form of 濡れる, ichidan) — also marks the new grammar
{
  "t": "濡れて",
  "r": "ぬれて",
  "role": "content",
  "word_id": "W00008",
  "is_new_grammar": true,
  "inflection": {
    "base": "濡れる",
    "base_r": "ぬれる",
    "form": "te",
    "word_id": "W00008",
    "grammar_id": "G007_te_form"
  }
}
```

The full inflection-form vocabulary (`polite_nonpast`, `te`, `past`, …) lives
in `pipeline/authoring_rules.md` Section 5.

### G6. Existing grammar can be re-introduced into authoring

If a grammar point is in `data/grammar_state.json` already (because an earlier
story shipped with it), you cannot list it in `plan.new_grammar`. But you
**should** still use it in the story whenever it's the right grammatical move.

The "give underused grammar real work" pattern (story 6 with `G002_ga_subject`)
is now a documented authoring move. Use `pipeline/lookup.py --grammar-usage`
to find candidates.

### G7. `new_grammar: []` is acceptable

Not every story needs to introduce a new grammar point. Story 6 introduced 2
new words and 0 new grammar — that earned more engagement budget for the cat
as the surprise. The validator does not require non-empty `new_grammar`.

### G8. `そして` (and other discourse connectors) belong in the JP, not just the gloss

If your English gloss for sentence N starts with "and then..." or "after
that...", the JP must contain the matching connector (そして, それから, etc.).
Otherwise you have **gloss inflation**: the English carries information the
Japanese does not. Story 3's first version had this; story 5 fixed the pattern
by introducing そして as a real textual chronology marker.

### G9. The reuse-quota rule is exempted only for the bootstrap story

`Check 6` requires ≥60% of content tokens to be drawn from words with
`occurrences < 5`. Story 1 (the bootstrap) is exempt because every word in
it is brand new. From story 2 onward, plan ahead: include enough lower-
occurrence reinforcement words to hit the threshold. `pipeline/lookup.py
--low-occ` lists the current pool.

### G10. The state updater is non-idempotent

Re-running `pipeline/run.py --step 4` on the same story will double-count
occurrences. The runner now refuses to update state if the story has already
shipped (it detects this by `story_id` in `vocab_state.first_story` /
`grammar_state.first_story`), but if you ever need to re-ship deliberately,
revert the state files from `state_backups/` first.

---

## When to consider adding a Japanese NLP library

These are intentionally NOT installed today. The friction they would solve
is not currently the bottleneck.

| Library                        | What it gives                                 | When to add it |
|--------------------------------|-----------------------------------------------|----------------|
| `fugashi` + `unidic-lite`      | Morphological analysis, auto-inflection      | When stories regularly use 5+ inflected forms per sentence |
| `jaconv`                       | kana ↔ romaji conversion                      | When the `reading` field becomes a frequent typo source |
| `pyopenjtalk`                  | Kana → mora-level pronunciation              | If we ever do per-mora audio alignment |
| `cutlet`                       | Romanization (Hepburn/Kunrei)                | If we expose romaji to learners |
| `sudachipy`                    | Tokenizer (alternative to fugashi)           | If fugashi's MIT-licensed dict is a problem |

The current 6-story library uses ~9 distinct inflected forms total; the
hand-authored `inflection` blocks remain easier than wiring a tokenizer.
Re-evaluate when the library hits ~30 stories.

---

## Authoring tooling — v0.3 (Japanese NLP backed)

As of v0.3 the authoring tools optionally use three Japanese NLP libraries
when installed (one-time `pip install -r requirements.txt`):

| Library | What it gives |
|---------|---------------|
| **fugashi + unidic-lite** | Morphological analysis: POS, lemma, reading, inflection form |
| **jaconv** | kana ↔ romaji conversion |
| **jamdict + jamdict-data** | JMdict lookup (English ↔ Japanese dictionary) |

Combined install footprint is ~80 MB (jamdict-data is ~50 MB of that).
All wrapped behind `pipeline/jp.py`, which falls back gracefully if any
library is missing — so the rest of the pipeline keeps working.

### What this unlocks in each tool

**`pipeline/precheck.py`**
- Real inflection check: `見ます` is now verified against
  `expected_inflection('みる', 'polite_nonpast', 'ichidan') = みます`.
  The validator's warning ("could not compute expected surface") becomes
  a hard error when the precheck engine *can* compute it and the surfaces
  disagree.
- Auto-derive `r` reading for kanji-bearing tokens via fugashi (under `--fix`).
- Detects "this looks like an inflected form but you forgot the
  inflection block" by trying every supported form against fugashi's
  output.

**`pipeline/scaffold.py`**
- New `--new-word-surfaces "猫,います"` flag auto-fills the
  `new_word_definitions` block with `kana`, `reading`, `pos`,
  `verb_class`, and primary English `meanings` from JMdict.
- For words not in JMdict (e.g. inflected forms like `光ります`), it
  leaves placeholders in place and the author fills them by hand.

**`pipeline/lookup.py`** — two new subcommands:
- `--jmdict <term>` — English↔Japanese dictionary search:
  ```bash
  python3 pipeline/lookup.py --jmdict cat
  python3 pipeline/lookup.py --jmdict 光る
  python3 pipeline/lookup.py --jmdict 帰る
  ```
- `--morph <text>` — morphological analysis (lemma / POS / reading /
  inflection form for every token):
  ```bash
  python3 pipeline/lookup.py --morph 'そして、猫がいます。'
  ```
  Useful for verifying that an inflected surface parses the way you
  expect before you commit to it in a story.

### `pipeline/jp.py` — public surface

If you write your own scripts:

```python
from jp import (
    JP_OK, which,           # capability introspection
    tokenize,               # fugashi morphological analysis
    derive_kana,            # 'X' (kanji) -> 'X' (hiragana)
    kana_to_romaji,         # 'ねこ' -> 'neko'
    katakana_to_hiragana,   # 'ネコ' -> 'ねこ'
    hiragana_to_katakana,
    has_kanji,
    expected_inflection,    # ('みる','polite_nonpast','ichidan') -> 'みます'
    jmdict_lookup,          # 'cat' or '猫' -> [DictEntry, ...]
)
```

Run `python3 pipeline/jp.py` for a self-test that prints capability
status and exercises every helper.

### Updated authoring loop

```bash
# 1. Plan — auto-fill new word fields from JMdict
python3 pipeline/scaffold.py plan \
    --title-jp 雪 --title-en "Snow" \
    --new-words 2 --new-grammar 0 \
    --new-word-surfaces "雪,降る"
# (now plan.json has '雪' kana=ゆき pos=noun and '降る' kana=ふる pos=verb/godan)

# 2. Fill in theme / setting / notes by hand, then validate
python3 pipeline/run.py --step 2

# 3. Story — scaffold inherits new_words from plan
python3 pipeline/scaffold.py story --sentences 7

# 4. Author tokens. When unsure of an inflection:
python3 pipeline/lookup.py --morph '雪が降ります。'
# (confirms 降り = 連用形-一般 of 降る godan; ます = 助動詞)

# 5. Pre-flight + auto-fix the cheap things
python3 pipeline/precheck.py --fix
# Now: idx, all_words_used, is_new placement, AND missing 'r' readings
# for any kanji-bearing token are all auto-filled.

# 6. Full validate, engagement review, ship + audio
python3 pipeline/run.py --step 3
python3 pipeline/engagement_review.py --mode print  # then fill review.json
python3 pipeline/engagement_review.py --mode finalize
python3 pipeline/run.py --step 4 --tts-backend google --tts-encoding MP3
```

### When NOT to enrich automatically

JMdict is comprehensive but not curated for graded-reader pedagogy. The
scaffolder always inserts an `_jmdict_pos` diagnostic field next to
auto-filled words — review it, then delete it before shipping. Common
edits the author should still make by hand:

- **Trim long meaning lists.** JMdict often returns 4-5 senses; pick
  the one your story actually uses.
- **Choose the right kanji.** Some words have multiple acceptable
  surfaces (e.g. `見る / 観る / 看る`); pick the one your story uses.
- **Verify verb_class.** Auto-detection from JMdict POS strings is
  best-effort; double-check against `pipeline/lookup.py --morph`.
- **Choose dictionary form.** JMdict almost always returns the
  dictionary form; if you wrote `光ります` instead of `光る` in
  `--new-word-surfaces`, expect a miss.
