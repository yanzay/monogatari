# Monogatari — System Specification

A graded-reader application for learning Japanese through short stories with guaranteed vocabulary control, click-to-lookup reading, and an integrated SRS reviewer.

## 1. Goals

- Hand-authored bilingual JP+EN prose becomes a fully tagged, lookup-aware story JSON automatically.
- Every Japanese token resolves to a stable vocabulary ID; every grammar surface to a stable grammar ID.
- The reader app is a static site that runs offline; no backend, no API keys at read time.
- The authoring pipeline is deterministic — no LLM API calls — so two authors with the same input get the same output.

## 2. Architecture

```
   bilingual JP+EN spec (one JSON per story)
             │
             ▼
   ┌─────────────────────┐
   │ pipeline/           │
   │   text_to_story.py  │ ← fugashi + UniDic + jamdict + jaconv
   └─────────┬───────────┘
             │
             ▼
   pipeline/story_raw.json (writer-stage shape)
             │
             ▼
   pipeline/validate.py     ← deterministic checks
             │
             ▼
   pipeline/audio_builder.py ← Google TTS, MP3 + per-token slices
             │
             ▼
   pipeline/state_updater.py ← cumulative vocab / grammar deltas
             │
             ▼
   stories/story_N.json + audio/story_N/  (shipped)
             │
             ▼
   index.html + js/app.js   (static reader)
```

The authoring pipeline runs locally on the developer's machine. The reader is a static bundle that consumes its output.

## 3. Data model

All artifacts are JSON; audio is MP3.

### 3.1 `data/vocab_state.json`

Cumulative vocabulary across all shipped stories. Carries **definition
metadata only**; attribution fields (`first_story`, `last_seen_story`,
`occurrences`) are derived from the corpus on-read by
`pipeline/derived_state.derive_vocab_attributions()` and projected to
`data/vocab_attributions.json` for the reader (Phase B, 2026-05-01).
Use `pipeline/_paths.load_vocab_attributed()` to get the joined view.

```jsonc
{
  "version": 1,
  "updated_at": "2026-05-01T16:48:00Z",
  "last_story_id": "story_10",
  "next_word_id": "W00079",
  "words": {
    "W00001": {
      "id": "W00001",
      "surface": "今朝",
      "kana":    "けさ",
      "reading": "kesa",                 // romaji aid
      "pos":     "noun",                 // noun | verb | i_adj | na_adj | adverb | …
      "verb_class": "godan",             // verbs only
      "meanings":   ["this morning"],
      "jlpt":       5,                   // optional difficulty cap signal
      "_minted_by": "story_1",           // immutable; first-introduction trace
      "notes": "Special reading けさ (NOT いまあさ)…"
      // NOTE: first_story / last_seen_story / occurrences live in
      // data/vocab_attributions.json, not here. See §3.7.
    }
  }
}
```

For verbs, `surface` is the **polite (masu) form**; `kana` is the polite-form reading.

### 3.2 `data/grammar_state.json`

Cumulative grammar inventory. Same Phase A contract as vocab_state:
**definition metadata only**; `intro_in_story` and `last_seen_story`
are derived from the corpus by
`derived_state.derive_grammar_attributions()` and projected to
`data/grammar_attributions.json`. Single id namespace as of
2026-05-01 — both state and catalog key by the catalog form
(`N5_wa_topic`, `N4_te_iku`, etc.); the legacy `G###_slug` ids
and the `catalog_id` join field were retired.

```jsonc
{
  "version": 1,
  "points": {
    "N5_wa_topic": {
      "id":    "N5_wa_topic",
      "title": "は — topic marker",
      "short": "Marks the topic of the sentence. Pronounced 'wa', not 'ha'.",
      "long":  "...",
      "jlpt":  "N5",
      "prerequisites": []
      // NOTE: intro_in_story / last_seen_story live in
      // data/grammar_attributions.json, not here. See §3.7.
    }
  }
}
```

### 3.3 `data/grammar_catalog.json`

Static reference catalog of all grammar points (built once from JLPT/Genki sources). Used by the converter to resolve surfaces to IDs and by the validator to enforce tier progression.

### 3.4 `stories/story_N.json` (shipped artifact)

```jsonc
{
  "story_id": 12,
  "title":    {"tokens": [ /* token records */ ]},
  "new_words":      ["W00045", "W00046"],
  "new_grammar":    ["N5_mashita"],
  "all_words_used": ["W00001", "W00002", "..."],   // first-seen order across title→sentences
  "sentences": [
    {
      "idx":      1,
      "gloss_en": "This morning, it is raining.",
      "tokens":   [ /* token records */ ]
    }
  ]
}
```

### 3.5 Token record

```jsonc
{
  "t":           "飲みました",      // surface
  "r":           "のみました",       // reading (hiragana). Required on kanji content tokens; optional on kana.
  "role":        "content",         // content | particle | aux
  "word_id":     "W00045",          // null/absent for pure-grammar tokens
  "grammar_id":  "N5_mashita", // optional; on the token, not inside `inflection`
  "is_new":      true,              // present + true on first occurrence in story; otherwise omitted
  "is_new_grammar": true,           // same convention for grammar
  "inflection": {                   // present for inflected verbs and select adjectives
    "base":       "飲む",            // dictionary surface
    "base_r":     "のむ",            // dictionary kana (always hiragana)
    "form":       "polite_past",    // see §4
    "verb_class": "godan"
  }
}
```

### 3.6 `learner_state.json` (browser localStorage)

SRS scheduler state, mastery tracking, and read-position bookmarks per device. Not synced.

### 3.7 `data/{vocab,grammar}_attributions.json` (derived projections)

Two derive-on-read manifest files written by `pipeline/build_{vocab,grammar}_attributions.py` from the corpus. **Single source of truth** for "where was this word/grammar point introduced" and "where was it last seen." Rebuilt automatically by `regenerate_all_stories.py --apply` (which is called from `step_write` on every successful ship).

```jsonc
// data/vocab_attributions.json
{
  "version": 1,
  "generated_at": "2026-05-01T16:48:00Z",
  "attributions": {
    "W00001": {
      "first_story":     "story_1",  // string; coerce via parse_story_id()
      "last_seen_story": "story_8",
      "occurrences":     19           // number of stories the word appears in
    }
  }
}

// data/grammar_attributions.json — same shape, intro_in_story instead
// of first_story; no occurrences field.
```

Reader joins these onto `vocab_state` / `grammar_state` at fetch time so call sites consuming `Word.first_story` see the joined view. Backend code uses `_paths.load_vocab_attributed()` (which overlays the projection) for the same convenience. Bypass paths (`_paths.load_vocab()`, raw `read_json(VOCAB)`) deliberately exist for state-write code that must NOT see the derived overlay.

**Why derived, not stored:** before Phase A+B (2026-05-01) these fields lived on the state files and drifted on every re-ship. The pre-Phase-B `occurrences` field had drifted LOW by 1–16 on 49 of 78 words, silently shipping wrong frequency counts to learners. Eliminating the storage made the bug class structurally impossible.

## 4. Schema conventions (v2 canonical)

### 4.1 Inflection forms

| `form`              | Example  | Notes                              |
|---------------------|----------|------------------------------------|
| `dictionary`        | 飲む       | Plain non-past (rarely tagged)     |
| `polite_nonpast`    | 飲みます    | The default for content stories    |
| `polite_past`       | 飲みました  | Tagged with `N5_mashita`    |
| `negative_polite`   | 飲みません  | Tagged with `N5_masen`           |
| `te`                | 飲んで     | Tagged with `N5_te_form`         |
| `ta`                | 飲んだ     | Plain past                          |
| `nai`               | 飲まない   | Plain negative                      |

The validator accepts `te_form` as an alias for `te`. The legacy v1/v3 names (`masu_polite_nonpast`, etc.) have been normalized away.

### 4.2 Roles

- `content` — carries lexical meaning; has `word_id`.
- `particle` — grammar surface (は, が, を, から, まで, etc.).
- `aux` — auxiliaries that combine with verbs/adjectives (ます, でした, ています glue, etc.).

### 4.3 Grammar tagging

`grammar_id` lives **on the token**, not inside `inflection`. Adjacent or compound forms (e.g. て + います) are split into two tokens — the verb in `te` form, and a separate `aux` token tagged `N5_te_iru`.

## 5. Validator (deterministic)

`pipeline/validate.py` runs a battery of checks on a story JSON:

1. **Schema** — all required fields present, types correct.
2. **Vocab resolution** — every `word_id` is in `vocab_state` or in this story's `new_words`.
3. **Grammar resolution** — every `grammar_id` is in `grammar_state` or `new_grammar`.
4. **First-seen order** — `all_words_used` matches the actual first occurrence across title→sentences.
5. **Inflection consistency** — when `inflection` is present, the surface kana matches what the inflection rules would produce from `base` + `form`.
6. **Reading sanity** — `r` is hiragana (no romaji); kanji tokens have a reading.
7. **Length tier** — total token count is within the policy band for the story's tier.
8. **Reuse quotas** — sufficient reuse of recent vocabulary.
9. **Gloss ratio** — EN gloss meaning-bearing words are within `[0.7, 3.0]` × JP meaning-bearing tokens.
10. **Grammar cadence** — at most N new grammar points per story; reinforcement of recent points.

Failures are surfaced with file paths, sentence indices, and exact mismatch detail.

## 6. Reader app

### 6.1 Stack

Vanilla JS, no build step. Renders `stories/index.json` as the table of contents and a single story JSON per Read view.

### 6.2 Views

- **Library** — story list with progress badges.
- **Read** — sentence-by-sentence with click-to-lookup (popup shows kana, gloss, grammar tag).
- **Review** — SRS queue driven by `learner_state.json`.

### 6.3 Offline

A service worker (`sw.js`) caches the static shell + the current story's JSON and audio.

## 7. Audio

`pipeline/audio_builder.py` calls Google Cloud TTS (`ja-JP-Standard-A` by default) and produces:

- `audio/story_N/sentence_M.mp3` — full sentence
- `audio/story_N/word_<word_id>.mp3` — per-vocab pronunciation, deduped by `word_id`

Audio paths and SHA hashes are written back into the story JSON so referential integrity is verifiable.

## 8. Tests

`pipeline/tests/` runs on every commit (via `.githooks/pre-commit`) and in CI. Categories:

- **Schema integrity** — vocab/grammar shape, no orphans.
- **Validator correctness** — every shipped story passes the validator.
- **Referential integrity** — audio file count matches sentence count; word_id audio matches vocab.
- **Pedagogical sanity** — all_words_used ordering, vocabulary reinforcement (Rule R1: ≥2 uses within 10 stories of introduction). The former Rule R2 (max 20-story gap) was retired 2026-04-24; late reuse of mature vocabulary is encouraged but not required. See `pipeline/tests/test_pedagogical_sanity.py::test_no_vocab_word_abandoned` for the rationale.
- **Determinism** — re-running the pipeline on the same input produces byte-identical output.

## 9. Open questions

- **Kanji introduction policy.** Current default: kana for stories 1-5, kanji-with-furigana from 6+, with a "hide furigana on known kanji" toggle planned for the reader.
- **Casual/plain register.** All shipped stories use polite (-masu) register. Plain-form stories are supported by the schema but not yet authored.
- **Multi-paragraph stories.** Currently single-paragraph; `sentences` is a flat list.
