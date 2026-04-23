# Monogatari — Authoring Guide

How to add a new story to the library.

## Overview

Authoring is **text-first**. You write a small bilingual JSON spec containing the Japanese prose and an English gloss per sentence; the converter turns it into a fully tagged story JSON, the validator checks it, the audio builder generates MP3s, and the state updater records the deltas.

```
your bilingual JP+EN spec
        │
        ▼
  text_to_story.py  →  validate.py  →  audio_builder.py  →  state_updater.py  →  shipped
```

No external LLMs are involved. All NLP is local: `fugashi` (UniDic) for tokenization, `jamdict` (JMDict) for dictionary lookups, `jaconv` for kana conversion.

## Prerequisites

```bash
pip install -r requirements.txt
# For audio generation:
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=<your-project-id>
```

## Step 1 — Write the bilingual spec

Create `pipeline/inputs/story_<N>.json` (the `inputs/` directory is for working drafts; gitignored):

```json
{
  "story_id": 68,
  "title":    {"jp": "雨", "en": "Rain"},
  "subtitle": {"jp": "静かな朝", "en": "A quiet morning"},
  "sentences": [
    {"jp": "今朝は雨です。",         "en": "This morning, it is raining."},
    {"jp": "私は窓から外を見ます。",   "en": "I look outside through the window."},
    {"jp": "木が濡れています。",       "en": "The trees are wet."},
    {"jp": "私はお茶を飲みます。",     "en": "I drink tea."}
  ],
  "new_word_meanings": {
    "雨": "rain"
  }
}
```

Notes:

- **`story_id`** must be the next free integer after the highest in `stories/`.
- **`sentences[].jp`** must end with `。` `！` or `？`.
- **`sentences[].en`** is your free-form translation. The validator's gloss-ratio check (Check 9) requires meaning-bearing English words to be within `[0.7, 3.0]` × meaning-bearing Japanese tokens — keep glosses concise.
- **`new_word_meanings`** is optional. Provide an explicit English meaning for any vocabulary word you expect to be new; otherwise the converter will fall back to the first JMDict sense (which is often acceptable but not always idiomatic).

## Step 2 — Convert text to story JSON

```bash
python3 pipeline/text_to_story.py pipeline/inputs/story_68.json \
    --out    pipeline/story_raw.json \
    --report pipeline/text_to_story.report.json
```

The converter:

1. Tokenizes each JP string with fugashi/UniDic.
2. Merges sub-tokens into canonical units (見+ます → 見ます, でし+た → でした, て+いる → te-aux).
3. Resolves each token to a `word_id` from `data/vocab_state.json` (matching by surface, kana, dictionary form, or polite-form kana).
4. Mints fresh `word_id`s for unrecognized vocabulary using your `new_word_meanings` or jamdict fallback.
5. Tags grammar surfaces (particles, copulae, te-form, polite-past, i-adj, etc.) with `grammar_id`s from `data/grammar_catalog.json`.
6. Emits `inflection` blocks (`base`, `base_r`, `form`, `verb_class`) for inflected verbs.
7. Marks `is_new` / `is_new_grammar` on first occurrences (deltas vs the cumulative state).

Read `pipeline/text_to_story.report.json` for any unresolved tokens, ambiguous grammar, or minted vocabulary.

## Step 3 — Validate

```bash
python3 pipeline/validate.py pipeline/story_raw.json
```

The validator runs the deterministic checks listed in [`spec.md` §5](spec.md#5-validator-deterministic). Common failure modes and fixes:

| Failure | Fix |
|---|---|
| **Check 5: Inflection mismatch** | Surface and the inflection's reading don't agree. Usually a homograph (e.g. UniDic picked 下りる for 降); fix by hand-editing `inflection.base` to the correct dictionary form. |
| **Check 7: Token count outside tier band** | Add or remove sentences to land in the policy range for this story_id. |
| **Check 9: Gloss ratio out of [0.7, 3.0]** | Your English is too terse or too verbose for the JP token count. Rewrite that sentence's gloss. |
| **Check 3.5: Grammar cadence exceeded** | You introduced more than the per-story budget of new grammar points. Split into two stories or substitute simpler patterns. |

Edit the spec, re-run step 2, re-validate. Iterate until clean.

## Step 4 — Generate audio

```bash
python3 pipeline/audio_builder.py pipeline/story_raw.json
```

This calls Google Cloud TTS once per sentence and once per **new** word_id (existing word audio is reused from `audio/`). Output goes to `audio/story_68/`. The script writes audio paths and SHA hashes back into the story JSON.

## Step 5 — Ship

```bash
cp pipeline/story_raw.json stories/story_68.json
python3 pipeline/state_updater.py stories/story_68.json
python3 pipeline/build_manifest.py    # rebuilds stories/index.json
python3 -m pytest pipeline/tests/     # final gate
```

`state_updater.py` increments `vocab_state.json` and `grammar_state.json` with the new entries and updates each affected word's `last_seen_story` / `occurrences`. Backups are written to `state_backups/` automatically.

## Authoring tools

### `pipeline/lookup.py` — vocab and grammar search

```bash
python3 pipeline/lookup.py 飲む                # find a word
python3 pipeline/lookup.py --by-kana のむ       # find by kana
python3 pipeline/lookup.py --reuse-preflight   # what should I reinforce?
python3 pipeline/lookup.py --grammar te-form   # find a grammar point
```

### `pipeline/precheck.py` — fast pre-flight

Lightweight version of the validator that surfaces the most common mistakes (missing readings, unknown surfaces, ratio violations) before you invoke the full pipeline.

```bash
python3 pipeline/precheck.py pipeline/story_raw.json
```

### `pipeline/text_to_story_roundtrip.py` — regression harness

Re-extracts each shipped story's bilingual prose, runs it back through the converter, and diffs against the canonical JSON. Used in CI.

```bash
python3 pipeline/text_to_story_roundtrip.py             # full library
python3 pipeline/text_to_story_roundtrip.py --story 12  # single story
python3 pipeline/text_to_story_roundtrip.py --strict    # exit nonzero on any diff
```

### `pipeline/normalize_to_v2.py` — schema normalizer

Idempotent in-place rewriter that brings any older v1/v3-shape stories to the canonical v2 schema (form-name aliases, romaji-r fixes, inflection field placement). Safe to run on the whole library; auto-backs-up to `state_backups/normalize_to_v2/`.

```bash
python3 pipeline/normalize_to_v2.py --dry-run   # preview
python3 pipeline/normalize_to_v2.py --apply     # apply
```

## Determinism guarantees

The converter is deterministic given the same input spec, vocab state, and grammar state. The round-trip harness verifies this on every commit: future changes to `text_to_story.py` cannot regress existing stories without a visible diff in CI.

What the converter **cannot** do automatically:

- **Translate** Japanese to English. You must supply the English glosses.
- **Disambiguate kanji homographs.** When UniDic picks the wrong base for words like 降りる/下りる, the converter emits a warning in the report and you fix `inflection.base` by hand (the validator will catch missed cases).
- **Choose register.** All current stories are polite (`-masu`); switching a story to plain form requires authoring it that way from the start.
- **Massage prose to satisfy pedagogical constraints.** Length, reuse quotas, and cadence are enforced by the validator; you adjust the input spec until checks pass.

## Adding a new grammar point

When your story uses a grammar surface not yet in `data/grammar_catalog.json`:

1. Add an entry to `data/grammar_catalog.json` with `id`, `title`, `short`, `long`, `genki_ref`, `jlpt`, `prerequisites`.
2. Add the surface→ID mapping to `SURFACE_TO_GRAMMAR` in `pipeline/text_to_story.py`.
3. Run `python3 pipeline/build_grammar_catalog.py` to refresh derived indices.
4. Re-run step 2 of the authoring flow.

## File layout for authoring

```
pipeline/
  inputs/                      # your working spec drafts (gitignored)
  story_raw.json               # last converter output
  text_to_story.report.json    # last converter report
state_backups/                  # automatic state snapshots
```

## Troubleshooting

**"surface not in vocab and no `new_word_meanings` entry"** — Either it's a typo, or you need to provide an explicit meaning. Add it to `new_word_meanings` in the spec.

**"unknown grammar surface"** — A particle or auxiliary you used isn't in the catalog. Add it (see "Adding a new grammar point") or rephrase.

**Converter produces a token you don't want** — UniDic occasionally over-segments or picks the wrong reading. Hand-edit `pipeline/story_raw.json` after the converter runs; subsequent stages (validate, audio, state) work on the edited file.

**Audio generation fails** — Confirm `gcloud auth application-default login` is current and `GOOGLE_CLOUD_PROJECT` is set. The first run for a story uploads ~one TTS request per sentence + per new word.

**Pytest fails after shipping** — Run `pipeline/normalize_to_v2.py --dry-run` to see if the new story drifts from v2 schema. If so, `--apply` to fix.
