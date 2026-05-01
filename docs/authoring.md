# Monogatari — Authoring Guide

How to add a new story to the library.

## Overview

Authoring is **text-first** and **source-of-truth**. You write a small bilingual JSON spec containing the Japanese prose and an English gloss per sentence; the converter turns it into a fully tagged story JSON, the validator checks it, the audio builder generates MP3s, and the state updater records the deltas.

```
pipeline/inputs/story_N.bilingual.json   ← THE source of truth (you edit this)
        │
        ▼ regenerate_all_stories.py --apply
        │
stories/story_N.json                     ← derived artifact (do not hand-edit)
        │
        ▼ validate.py → audio_builder.py → pytest
                  (stories/index.json is refreshed by the regenerator above)
        │
shipped
```

Key invariants:

- **`pipeline/inputs/*.bilingual.json` is the only source you edit.** The shipped JSON in `stories/` is a derived artifact of the bilingual spec plus `data/vocab_state.json` and `data/grammar_state.json`.
- **The regenerator is idempotent** — running it twice produces the same output.
- **`is_new`, `is_new_grammar`, `new_words`, `new_grammar`** are decided by a single library-wide first-occurrence pass that walks the shipped library in story-id order. There are no heuristics; the shipped library IS the source of truth for first-occurrence semantics.

No external LLMs are involved. All NLP is local: `fugashi` (UniDic) for tokenization, `jamdict` (JMDict) for dictionary lookups, `jaconv` for kana conversion.

## Prerequisites

> **⚠ Activate the project venv first — every time.**
> Every pipeline script (`text_to_story.py`, `regenerate_all_stories.py`,
> `validate.py`, `audio_builder.py`, `lookup.py`, `precheck.py`) depends on
> `fugashi` + `jamdict` + `jaconv`. If those imports fail under whichever
> Python you happen to invoke, `text_to_story.build_story` silently emits
> sentences with empty token arrays. The end-of-run orphan-vocab cleanup
> in `regenerate_all_stories.py` then concludes that *every* word is
> unreferenced and tries to delete `data/vocab_state.json`. The script now
> hard-fails on the missing-deps case (preflight import check + refuse to
> drop >50% of vocab as "orphans"), but the cleanest defence is the habit
> of always activating the venv before running anything in `pipeline/`.

```bash
# One-time setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Every shell session that touches pipeline/
source .venv/bin/activate

# For audio generation:
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=<your-project-id>
```

## Step 1 — Write the bilingual spec

Create `pipeline/inputs/story_<N>.bilingual.json`. This file is the source of truth — once it exists, the regenerator never overwrites it.

```json
{
  "story_id": 56,
  "title":    {"jp": "雨", "en": "Rain"},
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

## Step 2 — Regenerate

```bash
python3 pipeline/regenerate_all_stories.py --apply
```

The regenerator:

1. For each `pipeline/inputs/story_N.bilingual.json` (and any shipped story without one — bootstrap path), invokes `text_to_story.py` to convert prose → tagged JSON.
2. Mints fresh `word_id`s for unrecognized vocabulary, appending them to `data/vocab_state.json`.
3. Runs context-sensitive grammar tagging (interrogatives 何/誰/どこ/いつ/なぜ, kosoado あの/この/その/どの, the と思います/と言います quotative construction, ある/いる existence, counters 一人/二人).
4. Walks the entire library in story-id order and rewrites `is_new`, `is_new_grammar`, story-level `new_words`, and story-level `new_grammar` deterministically — no heuristics, no hints.
5. Rebuilds the derive-on-read attribution projections at `data/{vocab,grammar}_attributions.json` (Phase A+B, 2026-05-01). These manifests carry `first_story` / `last_seen_story` / `occurrences` for vocab and `intro_in_story` / `last_seen_story` for grammar. The state files themselves carry definition metadata only.
6. Writes timestamped backups to `state_backups/regenerate_all_stories/`. Auto-pruned to last 5 per stem on every successful ship via `step_write` (see SKILL.md §F).

The script is idempotent: a second `--apply` produces no changes when nothing has been edited.

For a single story (faster iteration), invoke the converter directly:

```bash
python3 pipeline/text_to_story.py pipeline/inputs/story_56.bilingual.json \
    --out pipeline/story_raw.json --report pipeline/text_to_story.report.json
```

…then read the report for any unresolved tokens or minted vocabulary, and run the regenerator once you're happy.

## Step 3 — Validate

```bash
python3 pipeline/validate.py stories/story_56.json
```

The validator runs the deterministic checks listed in [`spec.md` §5](spec.md#5-validator-deterministic). Common failure modes and fixes:

| Failure | Fix |
|---|---|
| **Check 5: Inflection mismatch** | Surface and the inflection's reading don't agree. Usually a homograph (e.g. UniDic picked 下りる for 降); add a `LEMMA_OVERRIDES` entry in `pipeline/text_to_story.py` and re-regenerate. |
| **Check 7: Token count outside tier band** | Add or remove tokens in the bilingual spec to land in the policy range for this story_id. |
| **Check 9: Gloss ratio out of [0.7, 3.0]** | Your English is too terse or too verbose for the JP token count. Rewrite that sentence's gloss. |

Edit `pipeline/inputs/story_<N>.bilingual.json`, re-run step 2, re-validate. Iterate until clean.

## Step 4 — Generate audio

```bash
python3 pipeline/audio_builder.py stories/story_56.json
```

This calls Google Cloud TTS once per sentence and once per **new** word_id (existing word audio is reused from `audio/`). Output goes to `audio/story_56/`. The script writes audio paths and SHA hashes back into the story JSON.

## Step 5 — Ship

```bash
python3 -m pytest pipeline/tests/     # final gate
```

`vocab_state.json`, `grammar_state.json`, and `stories/index.json` are all
refreshed automatically by the regenerator in step 2; you don't need to run
`state_updater.py` or `build_manifest.py` separately when using the
regenerator.

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

## Determinism guarantees

The converter and regenerator are deterministic given the same input spec, vocab state, and grammar state. Running `regenerate_all_stories.py --apply` twice in a row yields no changes when nothing has been edited, and the pytest suite gates structural integrity (`stories/`, `data/vocab_state.json`, `data/grammar_state.json` must agree).

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
  inputs/                      # bilingual JP+EN specs — SOURCE OF TRUTH (tracked in git)
  story_raw.json               # last single-story converter output (gitignored)
  text_to_story.report.json    # last single-story converter report (gitignored)
state_backups/                  # automatic state snapshots (gitignored)
```

## Troubleshooting

**"surface not in vocab and no `new_word_meanings` entry"** — Either it's a typo, or you need to provide an explicit meaning. Add it to `new_word_meanings` in the spec.

**"unknown grammar surface"** — A particle or auxiliary you used isn't in the catalog. Add it (see "Adding a new grammar point") or rephrase.

**Converter produces the wrong reading or base form** — UniDic occasionally picks a homograph. Add an entry to `LEMMA_OVERRIDES` or `READING_OVERRIDES` in `pipeline/text_to_story.py` and re-run the regenerator. Direct hand-edits to `stories/story_*.json` are NOT preserved — the next regenerator run overwrites them.

**Audio generation fails** — Confirm `gcloud auth application-default login` is current and `GOOGLE_CLOUD_PROJECT` is set. The first run for a story uploads ~one TTS request per sentence + per new word.

**Pytest fails after shipping** — Run `python3 pipeline/regenerate_all_stories.py` (dry-run, no `--apply`) to see what would change. If it shows pending diffs, the shipped library is stale; run `--apply`. The library-wide first-occurrence pass and vocab metadata refresh both run inside the regenerator, so a clean dry-run is the canonical "ready to ship" signal.
