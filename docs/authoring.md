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

---

## Length progression — v0.4

Stories grow gradually as the library grows, so a learner working through
the library is always slightly stretched but never jolted. The curve is
encoded in `pipeline/progression.py` and enforced by the validator's
Check 7.

### The curve

```
target_sentences(n)      = 7 + max(0, (n - 10 - 1) // 5 + 1)   for n > 10
target_content_tokens(n) = round(2.6 * target_sentences(n))
```

| Stories | Sentences | Content tokens | (delta) |
|---------|-----------|----------------|---------|
| 1–10    | 7         | 18             | (baseline plateau) |
| 11–15   | 8         | 21             | +1 sentence |
| 16–20   | 9         | 23             | +1 sentence |
| 21–25   | 10        | 26             | +1 sentence |
| 26–30   | 11        | 29             | +1 sentence |
| 31–35   | 12        | 31             | +1 sentence |
| ...     | ...       | ...            | ... |

By story 30 the learner is reading **57% longer** stories than at story 1,
but they got there in 5 imperceptible steps. Each step coincides with a
"tier" boundary every 5 stories.

### Tolerance

| | min | target | max |
|---|---|---|---|
| Sentences | target − 1 | _from curve_ | target + 1 |
| Content tokens | target × 0.7 | _from curve_ | target × 1.4 |

The 1.4× upper-bound on content tokens (rather than 1.3×) was calibrated
to admit story 4 (the densest in the existing library at 25 content tokens
for an 18-token target). Tightening to 1.3× would retroactively reject
already-shipped prose.

### How the pipeline enforces it

| Stage | Check |
|-------|-------|
| `lookup.py --next` | Surfaces the target sentences + content tokens for the next story. |
| `lookup.py --progression` | Prints the full curve up to story 35 with tier boundaries marked. |
| `scaffold.py plan` | Auto-fills `target_word_count` and `max_sentences` from the curve. |
| `scaffold.py story --sentences` | If omitted, defaults to the progression target for the plan's `story_id`. |
| `planner.py --validate` | Refuses plans whose `target_word_count` or `max_sentences` lies outside the band. |
| `validate.py` Check 7 | Hard-fails stories whose sentence count or content-token count is outside the per-story-id band. |

### What NOT to do

- **Don't bump `_BASELINE_PLATEAU`.** Stories 1–8 already shipped at 7
  sentences; raising the floor would invalidate existing prose.
- **Don't widen `CONTENT_HIGH` past 1.4×.** The current value is the
  tightest the existing library allows; widening it weakens the curve's
  whole purpose.
- **Don't tighten `SENTENCE_TOLERANCE` below 1.** The curve is supposed
  to give the author one beat of latitude. The tolerance is what makes
  a "+1 sentence step" a soft transition rather than a sudden jolt
  (story 11 at 8 sentences is fine; story 11 at 7 is also fine because
  it sits at the previous tier's max).

### Special story_id

`story_id == 0` is reserved for test fixtures and other in-pipeline uses
where the progression curve does not apply. Check 7 falls back to the
historic absolute sentence range (5..8) for these. Real shipped stories
must always have `story_id >= 1`.

---

## v0.5 — Reuse-quota drift fix (2026-04-22)

### The bug

`Check 6 (reuse quota)` requires that ≥60% of a story's content tokens come
from words with `occurrences < 5` in `vocab_state.json`. The intent is *"this
story is doing real reinforcement of under-practiced vocabulary."*

The bug: `occurrences` is a **lifetime total** that keeps climbing every time
a later story uses the same word. So:

- Story 5 ships in March → at the time, 私 had `occurrences=4` (low-occ).
- Story 5 (correctly) used 私 several times to satisfy the reuse quota.
- Stories 6, 7, 8 each use 私 a few more times → by April, 私 has `occurrences=12`.
- Re-validating Story 5 in April reads `occurrences=12` and counts 私 as
  HIGH-occ → reuse quota suddenly fails.

This caught my attention because *all 7 non-bootstrap shipped stories started
failing Check 6* after Story 8 shipped. They were perfectly valid at ship
time; they just got drifted-into-invalid by their own successors.

### The fix

`pipeline/validate.py` now computes **ship-time effective occurrences** for
every word it considers in Check 6:

```
effective_occ = lifetime_occ
              − (uses of this word in this story)
              − (uses of this word in every story with story_id > this one)
```

In the ship-time path (validator runs *before* `state_updater.py` bumps
counts), this evaluates to `lifetime_occ − this_story_uses` (no future
stories yet) — which matches what the validator was always trying to
measure. In the re-validate-an-old-story path, the formula recovers the
ship-time snapshot exactly.

### Sentinel for tests

`story_id == 0` is a test-fixture sentinel. When the validator sees it,
the discount is skipped — the test fixture is asking "what does Check 6
say if these words really are at this occurrence count?", which is the
correct semantics for unit tests.

### What this means in practice

- All 8 shipped stories now re-validate green at any point in the future,
  regardless of how many later stories pile uses onto their words.
- The CI loop in `pipeline/run.py` (which validates the new story before
  shipping it) is unchanged and unaffected.
- New stories must still satisfy the 60% quota at their own ship time —
  the rule is just measured correctly now.

### How to verify

```bash
python pipeline/validate.py stories/story_5.json   # ✓ VALID (was ✗ INVALID before fix)
python pipeline/test_validate.py                    # 50/50 ✓ (2 new tests for the drift fix)
```

---

## v0.6 — Masu-form auto-derivation in scaffold (2026-04-22)

### The gap

When authoring story 9 I had to hand-fill the `寝ます` definition because
JMdict only indexes verbs in their dictionary form (`寝る`). The scaffold
helper would return `None` for any masu-form input, defeating the
auto-fill purpose for the most common shape of "new verb" in the
authoring loop.

### The fix

`pipeline/scaffold.py` now does a two-stage lookup for any
`--new-word-surface` ending in ます:

1. Try direct JMdict lookup (works for nouns, adjectives, dictionary-form
   verbs).
2. If that misses and the surface ends in ます, derive **both** the
   ichidan candidate (`寝ます → 寝る`) and the godan candidate
   (`読みます → 読む`), look each up, and accept the first one whose
   POS contains "verb" *and* matches the candidate's verb class.

When the dictionary form hits, scaffold:
- Pulls the dictionary-form kana from JMdict (`ねる` / `よむ`).
- Re-derives the masu-form kana by inverting the same transformation
  (`ねる → ねます`, `よむ → よみます`).
- Locks the verb class (ichidan/godan) from the candidate that matched.
- Tags `_jmdict_pos` with the derivation chain
  (`"ichidan verb (derived via 寝る/ichidan)"`) so the diagnostic is
  visible in the generated plan.json.

### Coverage

Confirmed working on:

| Surface   | Class    | kana       | reading      |
| --------- | -------- | ---------- | ------------ |
| 寝ます     | ichidan  | ねます      | nemasu       |
| 食べます   | ichidan  | たべます    | tabemasu     |
| 見ます     | ichidan  | みます      | mimasu       |
| 飲みます   | godan    | のみます    | nomimasu     |
| 読みます   | godan    | よみます    | yomimasu     |
| 歩きます   | godan    | あるきます  | arukimasu    |
| 帰ります   | godan    | かえります  | kaerimasu    |
| 行きます   | godan    | いきます    | ikimasu      |
| 話します   | godan    | はなします  | hanashimasu  |
| 立ちます   | godan    | たちます    | tachimasu    |

All 9 godan endings (う/く/ぐ/す/つ/ぬ/ぶ/む/る) are mapped.

### What this changes about the authoring loop

Before story 9: any verb new-word required either hand-filling
verb_class + kana, or feeding scaffold the dictionary form (and then
re-typing the polite form into the story). Either way, a typo-prone
manual step.

From story 10 onward: `--new-word-surfaces "X,Y,寝ます"` works as a
single drop-in command for any combination of nouns, adjectives,
dictionary-form verbs, and polite-form verbs. The scaffold will
classify and inflect each correctly without further intervention.

### Limitations

- Surface-form ます with no kanji at all (e.g. plain あります) is rare in
  practice but would still hit the fallback path; outcome depends on
  whether JMdict has a class-confirmed candidate.
- 来ます (kuru, irregular) and します (suru, irregular) will be
  ichidan-classified by the candidate generator, but JMdict marks them
  as irregular — the verb class lock falls back to ichidan in that
  case. If the library ever needs an irregular verb as a new word, that
  one definition would still need a hand fix. (Not a blocker today; we
  have no irregular verbs in the upcoming queue.)

---

## v0.7 — Fugashi-backed verb classification (handles irregulars)

### What v0.6 left on the table

The masu-form fallback I added in v0.6 was bespoke string-rewriting that
worked for ichidan + all 9 godan endings, but had two real limitations:

1. **Irregular verbs** (来る, する) couldn't be classified — JMdict tags them
   as "irregular" rather than ichidan/godan, and my candidate generator
   only knew those two classes.
2. **Suru-compounds** (勉強します, 散歩します) had no story at all — my
   candidates would only try `勉強する → 勉強る` (ichidan attempt, no hit)
   and a non-existent godan candidate.

### What changed

`pipeline/jp.py` now exports `analyze_verb(surface)` that does
**all** the verb-shape analysis from a single fugashi pass:

```python
analyze_verb("寝ます")
# → {lemma: 寝る, lemma_kana: ねる, masu_kana: ねます,
#    verb_class: ichidan, conj_type: 下一段-ナ行, ...}

analyze_verb("勉強します")
# → {lemma: 勉強する, lemma_kana: べんきょうする, masu_kana: べんきょうします,
#    verb_class: irregular_suru, ...}
```

Mapping from UniDic conjugation type to our taxonomy:

| UniDic cType   | Our `verb_class`     | Examples              |
| -------------- | -------------------- | --------------------- |
| 五段-X行       | godan                | 飲む, 読む, 立つ, 帰る   |
| 上一段-X行     | ichidan              | 見る, いる            |
| 下一段-X行     | ichidan              | 食べる, 寝る           |
| カ行変格       | irregular_kuru       | 来る (only)           |
| サ行変格       | irregular_suru       | する + all suru compounds |

`pipeline/scaffold.py:_enrich_word_from_jmdict` is now fugashi-first for
verbs (UniDic gets the verb_class right; JMdict is only consulted for
the English meaning), JMdict-only for non-verbs. The bespoke ます-stem
mapping table from v0.6 is retired.

### Validator-side: irregular conjugation

`pipeline/validate.py:conjugate` now has small total tables for
`irregular_kuru` and `irregular_suru` so the validator can verify
inflected surfaces of irregular verbs once they ship. Suru-compound
support is structural — `conjugate("勉強する", "polite_nonpast", "irregular_suru")`
returns `勉強します` by stripping the trailing する and re-attaching
the irregular suffix.

Forms covered: dictionary, polite_nonpast (= masu), polite_past,
polite_negative, te, ta, nai/negative.

### End-to-end coverage today

`pipeline/scaffold.py plan --new-word-surfaces "X,Y,Z"` now handles
**any** combination of:

- nouns (椅子, 机, 朝, 卵, ...)
- i-adjectives (温かい, 静か, ...)
- ichidan verbs (寝ます, 食べます, 見ます, います, ...)
- godan verbs (飲みます, 読みます, 歩きます, あります, ...)
- irregular_kuru (来ます)
- irregular_suru (します)
- suru-compounds (勉強します, 散歩します)

…with no hand intervention. The dictionary form, masu form kana,
romaji, verb_class, and POS are all populated automatically and
correctly. JMdict is the sole source of English meanings; if JMdict
has no entry for a suru-compound (it usually only indexes the noun
half), the meaning slot is left as a `<primary English meaning>`
placeholder for the author to fill — the only remaining hand step.

---

## v0.8 — Pipeline consolidation: single inflection engine, suru-compound meaning synthesis

### Two long-standing duplications resolved

The codebase had **two inflection engines** quietly diverging:

1. `pipeline/jp.py:expected_inflection` — fugashi/UniDic-aware, knew about
   irregulars but mishandled `行く` (returned 行いて instead of 行って).
2. `pipeline/validate.py:conjugate` — knew about `行く` (had a special case
   table) but didn't accept the canonical `polite_nonpast` form name and
   couldn't compute masu form for ichidan verbs at all.

Result: **every shipped story emitted the same warning** —
`Could not compute expected surface for base='見る' form='polite_nonpast' — skipping`.
The Check 5 inflection check was effectively a no-op for masu-form verbs
across all 9 stories.

### What changed

`pipeline/validate.py:conjugate` now **delegates to
`jp.expected_inflection` first**, falling back to its local tables only
for forms jp.py doesn't cover (potential, volitional, etc.). One source
of truth, one place to fix bugs.

`pipeline/jp.py:expected_inflection` now also handles:
- **`行く` / `いく`** — special godan: te-form is 行って, past is 行った.
- **Suru-compounds** — `勉強する` / `散歩する` / `為る` are routed by
  stripping the trailing する/為る and recursing for the irregular suru
  suffix. `expected_inflection("勉強する", "polite_nonpast", "irregular_suru")`
  now returns `勉強します` directly.

### Suru-compound meaning synthesis (the v0.7 follow-up)

`pipeline/scaffold.py:_enrich_word_from_jmdict` now synthesizes a "to X"
verb meaning when it encounters an irregular_suru with a non-trivial
prefix (e.g. 勉強します). Process:

1. Strip the trailing する/為る from the lemma → noun (勉強).
2. Look up the noun in JMdict.
3. Take the first synonym from the first sense (split on `;` to avoid
   "to cooking; cookery; cuisine; ...").
4. If the synonym is a single-word `-ing` nominalization (cooking,
   cleaning, exercising), strip the suffix to get the bare verb.
5. Prepend "to ".

Confirmed end-to-end:

| Surface       | Synthesized meaning   |
| ------------- | --------------------- |
| 勉強します    | to study              |
| 散歩します    | to walk               |
| 料理します    | to cook               |
| 掃除します    | to clean              |
| 運動します    | to exercise           |
| 電話します    | to telephone call     |

The last one ("to telephone call") is awkward but technically not wrong;
authors can refine to "to make a phone call" post-hoc. The point of v0.8
is that scaffold no longer leaves a `<primary English meaning>`
placeholder for any common verb shape.

### Side effect: warning-free shipping

After this change, **every shipped story re-validates with zero warnings**:

```
story 1: ✓ VALID (warnings: 0)
story 2: ✓ VALID (warnings: 0)
…
story 9: ✓ VALID (warnings: 0)
```

The Check 5 warning was structural, not content-driven — it was firing
on correctly-authored verbs because the validator's lookup couldn't
find them. Now that gap is closed.

### Verification

- 50/50 unit tests pass
- `conjugate` and `expected_inflection` agree on all 11 test cases
  including all 4 irregular forms and one suru-compound
- All 9 stories ✓ VALID, 0 warnings each

---

## v0.9 — Grammar tier progression (JLPT-aligned)

### What changed

A new pacing dimension joins length progression: **grammar tier progression**.
Where `pipeline/progression.py` governs *how long* a story may be at story_id N,
the new `pipeline/grammar_progression.py` governs *which grammar points may be
introduced*.

### The tier ladder

| Tier | JLPT | Story window | Meaning |
|------|------|--------------|---------|
| 1    | N5   | 1–10         | Foundation: copula, particles, te-form, te-iru, basic connectives |
| 2    | N4   | 11–25        | Tense + negation: past, negatives, ~たい (want), ~から (because), simple adverbs |
| 3    | N3   | 26–50        | Intent + conditionals: ~ましょう, ~たら, ~ば, ~つもり, comparison, time clauses |
| 4    | N2+  | 51+          | Embedded clauses, passive/causative, honorifics, advanced connectives |

JLPT is used as a **reference framework only** — we don't claim to teach the
exam. It's the closest commonly-understood ladder, and it eliminates the
"is this beginner or intermediate?" judgment call.

### The rule (Check 3.5)

A story's `new_grammar` may come from the **current tier or earlier**.
Cross-tier introductions (jumping ahead) are blocked at validation time —
hard block, consistent with how Check 7 length progression works.

Earlier-tier grammar is always legal: story 50 may absolutely introduce a
previously-skipped N5 particle if the right narrative context arises. The
block is one-directional (no jumping ahead, never backward).

### How to use it

- `python3 pipeline/lookup.py --next` now prints the next story's tier and
  flags JLPT tier transitions.
- `python3 pipeline/lookup.py --grammar-progression` prints the full ladder.
- `pipeline/scaffold.py plan` pre-fills the `jlpt:` field on any new
  grammar definition with the level currently active for the next story.
- `pipeline/validate_state.py` now requires `jlpt` on every grammar point
  (must be one of N5/N4/N3/N2/N1).

### Migration

All 12 existing grammar points were tagged `jlpt: "N5"` (they fit cleanly
into Tier 1). Story 11 will be the first to draw from N4.
