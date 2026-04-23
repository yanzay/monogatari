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

Cumulative vocabulary across all shipped stories.

```jsonc
{
  "version": 1,
  "updated_at": "2026-04-23T22:00:00Z",
  "last_story_id": 67,
  "next_word_id": "W00251",
  "words": {
    "W00001": {
      "id": "W00001",
      "surface": "今朝",
      "kana":    "けさ",
      "reading": "kesa",                 // romaji aid
      "pos":     "noun",                 // noun | verb | i_adj | na_adj | adverb | …
      "verb_class": "godan",             // verbs only
      "meanings":   ["this morning"],
      "first_story":     "story_1",
      "last_seen_story": "story_31",
      "occurrences":     9,
      "notes": "Special reading けさ (NOT いまあさ)…"
    }
  }
}
```

For verbs, `surface` is the **polite (masu) form**; `kana` is the polite-form reading.

### 3.2 `data/grammar_state.json`

Cumulative grammar inventory.

```jsonc
{
  "version": 1,
  "points": {
    "G001_wa_topic": {
      "id":    "G001_wa_topic",
      "title": "は — topic marker",
      "short": "Marks the topic of the sentence. Pronounced 'wa', not 'ha'.",
      "long":  "...",
      "genki_ref":     "L1",
      "first_story":   "story_1",
      "prerequisites": [],
      "jlpt": "N5"
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
  "subtitle": {"tokens": [ /* token records */ ]},
  "new_words":      ["W00045", "W00046"],
  "new_grammar":    ["G013_mashita_past"],
  "all_words_used": ["W00001", "W00002", "..."],   // first-seen order across title→subtitle→sentences
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
  "grammar_id":  "G013_mashita_past", // optional; on the token, not inside `inflection`
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

## 4. Schema conventions (v2 canonical)

### 4.1 Inflection forms

| `form`              | Example  | Notes                              |
|---------------------|----------|------------------------------------|
| `dictionary`        | 飲む       | Plain non-past (rarely tagged)     |
| `polite_nonpast`    | 飲みます    | The default for content stories    |
| `polite_past`       | 飲みました  | Tagged with `G013_mashita_past`    |
| `negative_polite`   | 飲みません  | Tagged with `G036_masen`           |
| `te`                | 飲んで     | Tagged with `G007_te_form`         |
| `ta`                | 飲んだ     | Plain past                          |
| `nai`               | 飲まない   | Plain negative                      |

The validator accepts `te_form` as an alias for `te`. The legacy v1/v3 names (`masu_polite_nonpast`, etc.) have been normalized away.

### 4.2 Roles

- `content` — carries lexical meaning; has `word_id`.
- `particle` — grammar surface (は, が, を, から, まで, etc.).
- `aux` — auxiliaries that combine with verbs/adjectives (ます, でした, ています glue, etc.).

### 4.3 Grammar tagging

`grammar_id` lives **on the token**, not inside `inflection`. Adjacent or compound forms (e.g. て + います) are split into two tokens — the verb in `te` form, and a separate `aux` token tagged `G008_te_iru`.

## 5. Validator (deterministic)

`pipeline/validate.py` runs a battery of checks on a story JSON:

1. **Schema** — all required fields present, types correct.
2. **Vocab resolution** — every `word_id` is in `vocab_state` or in this story's `new_words`.
3. **Grammar resolution** — every `grammar_id` is in `grammar_state` or `new_grammar`.
4. **First-seen order** — `all_words_used` matches the actual first occurrence across title→subtitle→sentences.
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
- **Pedagogical sanity** — all_words_used ordering, vocabulary reinforcement, no abandoned words.
- **Determinism** — re-running the pipeline on the same input produces byte-identical output.

## 9. Open questions

- **Kanji introduction policy.** Current default: kana for stories 1-5, kanji-with-furigana from 6+, with a "hide furigana on known kanji" toggle planned for the reader.
- **Casual/plain register.** All shipped stories use polite (-masu) register. Plain-form stories are supported by the schema but not yet authored.
- **Multi-paragraph stories.** Currently single-paragraph; `sentences` is a flat list.
