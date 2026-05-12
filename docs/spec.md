# Monogatari — System Specification

A graded-reader application for learning Japanese through short stories with guaranteed vocabulary control, click-to-lookup reading, and an integrated SRS reviewer.

## 1. Goals

- Bilingual JP+EN prose specs become fully tagged, lookup-aware story JSON automatically and deterministically.
- Every Japanese token resolves to a stable vocabulary ID; every grammar surface to a stable grammar ID.
- The reader app is a SvelteKit PWA that runs fully offline; no backend, no API keys at read time.
- The authoring pipeline is deterministic — the same input spec + state always produces the same output.
- Stories are authored by an LLM agent running `pipeline/author_loop.py`; no hand-authoring.

## 2. Architecture

```
pipeline/inputs/story_N.bilingual.json   ← editable spec (source of truth)
             │
             ▼
   pipeline/author_loop.py author N      ← the only sanctioned ship path
             │
             ├─ text_to_story.py         (fugashi + UniDic + jamdict + jaconv)
             ├─ validate.py              (Checks 1–11, deterministic)
             ├─ mint_budget              (per-story vocab cap)
             ├─ pedagogical_sanity       (grammar reinforcement debt)
             ├─ vocab_reinforcement      (R1 window enforcement)
             ├─ coverage_floor           (JLPT tier grammar floor)
             ├─ state_updater.py         (mints W-IDs, writes vocab/grammar state)
             ├─ regenerate_all_stories.py --story N --apply  (is_new flags)
             └─ audio_builder.py         (Google TTS, per-sentence + per-word MP3)
             │
             ▼
stories/story_N.json + audio/story_N/ + audio/words/   (shipped)
             │
             ▼
   SvelteKit static build → static/    (reader app)
```

All gauntlet steps are hard-block — a failure does not ship the story.

The literary-review gate is an **in-skill discipline** (SKILL.md §B.0/B.1/§E.5/E.6/E.7/E.7.5/§G) that the agent runs before `author_loop.py author N --live`. No `pipeline/literary_review.py` exists; the gate runs through the agent's own reasoning prior to the deterministic gauntlet.

## 3. Data model

All artifacts are JSON; audio is MP3.

### 3.1 `data/vocab_state.json`

Cumulative vocabulary across all shipped stories. Carries **definition metadata only**; attribution fields (`first_story`, `last_seen_story`, `occurrences`) are derived from the corpus on-read by `pipeline/derived_state.derive_vocab_attributions()` and projected to `data/vocab_attributions.json` (Phase B, 2026-05-01).

Use `pipeline/_paths.load_vocab_attributed()` to get the joined view. Raw `load_vocab()` is reserved for state-write paths that must not see the derived overlay.

```jsonc
{
  "version": 1,
  "updated_at": "2026-05-01T16:48:00Z",
  "last_story_id": "story_15",
  "next_word_id": "W00099",
  "words": {
    "W00001": {
      "id":       "W00001",
      "surface":  "今朝",           // kanji/kana display form; hiragana for grammaticalized verbs
      "kana":     "けさ",
      "reading":  "kesa",           // romaji aid
      "pos":      "noun",           // noun | verb | i_adj | na_adj | adverb | conjunction | …
      "verb_class": "godan",        // verbs only
      "meanings": ["this morning"],
      "jlpt":     5,                // JLPT level (5=N5); from data/jlpt_vocab.json
      "nf_band":  "nf06",           // frequency band; used for lexical difficulty cap
      "_minted_by": "story_1",      // immutable; first-introduction trace
      "notes": "Special reading けさ (NOT いまあさ)…"
    }
  }
}
// NOTE: first_story / last_seen_story / occurrences live in
// data/vocab_attributions.json, NOT here.
```

**Mint guard:** `surface` uses the on-page form (hiragana for grammaticalized verbs like ある/いる/する). Kanji lemma is only kept if the corpus actually uses kanji in the text.

**Conjunction vocab:** surfaces in `text_to_story.CONJUNCTION_VOCAB` (だから, ですから, でも, そして, について) mint as `pos=conjunction` records and get BOTH `word_id` AND `grammar_id`. They flow through `report["new_function_words"]` and do not count against the mint budget.

### 3.2 `data/grammar_state.json`

Cumulative grammar inventory. **Definition metadata only** — `intro_in_story` and `last_seen_story` are derived from the corpus by `derived_state.derive_grammar_attributions()` and projected to `data/grammar_attributions.json` (Phase A, 2026-05-01).

Single id namespace: both state and catalog key by the catalog form (`N5_wa_topic`, `N4_te_iku`, etc.). The legacy `G###_slug` ids and `catalog_id` join field are retired.

```jsonc
{
  "version": 1,
  "points": {
    "N5_wa_topic": {
      "id":          "N5_wa_topic",
      "title":       "Topic marker は",
      "short":       "Xは — marks the topic of the sentence",
      "long":        "…",
      "jlpt":        5,
      "marker":      "は",
      "category":    "particle",
      "sources":     ["Genki I §2"]
    }
  }
}
// NOTE: intro_in_story / last_seen_story live in
// data/grammar_attributions.json, NOT here.
```

Grammar points not yet in `grammar_state.json` but auto-tagged by the pipeline are registered in `text_to_story.KNOWN_AUTO_GRAMMAR_DEFINITIONS` so `state_updater` can attribute them on first use.

### 3.3 `data/grammar_catalog.json`

The canonical grammar-point registry — definition-level metadata (title, short, long, jlpt, prerequisites, sources). Keys are the same catalog-form ids used in `grammar_state.json`. The pipeline's `build_grammar_catalog.py` derives indices from it.

### 3.4 `data/vocab_attributions.json` and `data/grammar_attributions.json`

Derived-on-read projections. Written by `pipeline/build_vocab_attributions.py` and `pipeline/build_grammar_attributions.py` (both called automatically by `regenerate_all_stories.py --apply`). Never edited by hand.

```jsonc
// data/vocab_attributions.json
{
  "attributions": {
    "W00001": {
      "first_story":     "story_1",
      "last_seen_story": "story_15",
      "occurrences":     12          // number of stories the word appears in
    }
  }
}

// data/grammar_attributions.json — same shape:
// intro_in_story, last_seen_story (no occurrences field)
```

The reader joins these onto `vocab_state` / `grammar_state` at fetch time. A 404 on the projection falls back gracefully (nothing introduced) rather than crashing.

**Why derived, not stored:** before Phase A+B these fields lived on the state files and drifted on every re-ship. The pre-Phase-B `occurrences` field had drifted LOW by 1–16 on 49 of 98 words. Eliminating the storage made the bug class structurally impossible.

### 3.5 `data/jlpt_vocab.json`

~280 KB lookup table (sourced from stephenmk/yomitan-jlpt-vocab). Used by `pipeline/lexical_difficulty.py` at mint time to assign `jlpt` and `nf_band` to new words.

Four lookup keys: `by_jmdict_seq`, `by_kanji_kana`, `by_kanji`, `by_kana`. Specific keys are tried first; loose keys are fallbacks.

### 3.6 `data/v2_5_seed_plan.json`

Prescribes specific words and grammar points to specific story slots (stories 1–10). Surfaced in `agent_brief.py` as `must_mint_from_seed`, hard-blocked by the gauntlet's `mint_budget` step.

### 3.7 `stories/story_N.json`

Derived artifact — do not hand-edit. Produced by `text_to_story.build_story()`. Key top-level fields:

```jsonc
{
  "story_id":   1,
  "title":      {"jp": "…", "en": "…"},
  "intent":     "…",           // required v2 field: one-sentence authorial intent
  "scene_class": "home_morning", // required v2 field; from scene_affordances.json
  "anchor_object": "窓",        // required v2 field; appears in ≥3 sentences
  "new_words":  ["W00001", …],  // story-level first-occurrences
  "new_grammar": ["N5_wa_topic", …],
  "sentences":  [
    {
      "jp":    "今朝は雨です。",
      "en":    "This morning it is raining.",
      "role":  "setting",      // required v2 field: setting|action|dialogue|inflection|reflection|closer
      "tokens": [ … ]
    }
  ]
}
```

### 3.8 Audio layout

- `audio/story_N/s<idx>.mp3` — per-sentence audio (story-scoped)
- `audio/words/<wid>.mp3` — per-word audio, **flat** (decoupled from story; a word's audio is reusable from review/library/popups)

The flat `audio/words/` layout was adopted 2026-04-29. The legacy per-story word audio layout (`audio/story_N/w_W*.mp3`) is no longer produced.

## 4. Schema conventions

### 4.1 Token shape

```jsonc
{
  "surface":    "飲みます",
  "r":          "のみます",       // hiragana reading
  "role":       "content",        // content | particle | aux
  "word_id":    "W00043",         // content tokens only
  "grammar_id": "N5_masu",        // optional; any token
  "is_new":     true,             // first corpus occurrence of this word_id
  "is_new_grammar": false,
  "inflection": {                 // content verbs/adjectives
    "base":  "飲む",
    "form":  "polite_nonpast"
  }
}
```

### 4.2 Inflection forms

| `form`            | Example   | Notes                          |
|-------------------|-----------|--------------------------------|
| `dictionary`      | 飲む      | Plain non-past                 |
| `polite_nonpast`  | 飲みます  | Default register in v2 corpus  |
| `polite_past`     | 飲みました | Tagged `N5_mashita`           |
| `negative_polite` | 飲みません | Tagged `N5_masen`             |
| `te`              | 飲んで    | Tagged `N5_te_form`           |
| `ta`              | 飲んだ    | Plain past                     |
| `nai`             | 飲まない  | Plain negative                 |

The validator accepts `te_form` as an alias for `te`.

### 4.3 Token roles

- `content` — carries lexical meaning; has `word_id`.
- `particle` — grammar surface (は, が, を, から, まで, etc.).
- `aux` — auxiliaries (ます, でした, ています glue, etc.).

### 4.4 Grammar tagging

`grammar_id` lives **on the token**, not inside `inflection`. Adjacent or compound forms (e.g. て + います) split into two tokens — the verb in `te` form, and a separate `aux` token tagged `N5_te_iru`.

### 4.5 Required v2 spec fields

Every bilingual spec must declare:
- `intent` — one-sentence authorial intent
- `scene_class` — one of the values in `data/scene_affordances.json`
- `anchor_object` — a JP noun appearing in ≥3 sentences
- Per-sentence `role` ∈ `{setting, action, dialogue, inflection, reflection, closer}`

## 5. Validator (deterministic)

`pipeline/validate.py` runs a battery of checks via `validate(story, vocab, grammar)` → `ValidationResult` with `.valid`, `.errors`, `.warnings`.

| Check | What it verifies |
|-------|-----------------|
| 1 | Schema — all required fields present, correct types |
| 2 | Closed vocabulary — every `word_id` is in `vocab_state` or this story's `new_words` |
| 3 | Closed grammar — every `grammar_id` is in `grammar_state` or `new_grammar` |
| 3.5 | Grammar tier progression — JLPT-aligned ordering |
| 3.6 | Grammar cadence — rolling-window max per story |
| 3.7 | Vocabulary cadence floor — min new words per story (post-bootstrap) |
| 3.8 | Grammar reinforcement — each new point reappears in next 5 stories |
| 3.9 | Tier coverage gate — no advancing to next JLPT tier until current tier is complete |
| 3.10 | Per-story grammar floor — post-bootstrap stories must introduce ≥1 new grammar point until tier is covered |
| 4 | Budget — mint count within the per-story ladder |
| 5 | Surface ↔ ID consistency + inflection correctness |
| 6 | Reinforcement floor — library-wide vocabulary reuse |
| 7 | Length progression — token count within the policy band for this story's tier |
| 8 | *(removed — intentional no-op stub, kept for numbering stability)* |
| 9 | Gloss sanity — EN gloss ratio within `[0.7, 3.0]` × JP meaning-bearing tokens |
| 11 | Semantic-sanity lint — wraps `pipeline/semantic_lint.py` rules 11.1–11.10 |

### 5.1 Semantic lint rules (Check 11)

All rules live in `pipeline/semantic_lint.py`. Each returns `Issue(severity, location, message)` with `severity` ∈ `{error, warning}`.

| Rule | Name | Severity |
|------|------|----------|
| 11.1 | inanimate-thing-is-quiet (静か on non-place noun + です/だ) | error |
| 11.2 | tomorrow's-X-consumed-today | warning |
| 11.3 | bare-known-fact (〜と思います on already-asserted time/weather, narrow) | warning |
| 11.4 | word_id ↔ surface lemma mismatch | error |
| 11.5 | lonely scene noun (scene noun appears only once with no action) | warning |
| 11.6 | location-を with noun list joined by と | error |
| 11.7 | closer noun-pile (last sentence = nouns + です, no verb) | error |
| 11.8 | tautological possessive equivalence (XのY は ZのY です) | error |
| 11.9 | bare-known-fact extended (broadens 11.3 to full embedded clauses) | warning |
| 11.10 | misapplied-quiet adverbial (静かに on same inanimate nouns as 11.1) | warning |

## 6. Pedagogical progression

### 6.1 Lexical difficulty cap

Newly-minted vocabulary is capped by the story's position in the corpus. A word passes if it satisfies **either** the JLPT level **or** the nf-band signal.

| Stories | JLPT cap | nf-band cap |
|---------|----------|-------------|
| 1–10 (bootstrap) | N5 | nf06 (~rank 3,000) |
| 11–25 | N4 | nf12 (~rank 6,000) |
| 26–50 | N3 | nf24 (~rank 12,000) |
| 51+ | N2 | nf48 (any) |

Words with no JLPT entry but with the `ichi1` tag (Ichimango basic vocab) are rescued — catches Tanos gaps like りんご, バナナ, かばん.

A spec may declare `lexical_overrides: ["surface", …]` to absorb up to **2** above-cap mints per story. More than 2 overrides → gauntlet hard-fails; split the scene instead.

### 6.2 Vocabulary reinforcement (Rule R1)

Every newly-minted word must reappear in at least one of the next 10 stories (`VOCAB_REINFORCE_WINDOW = 10`). The gauntlet's `vocab_reinforcement` step enforces this at the **last slot only** (story = intro + 10): it is a hard block only when the window is about to close and the word has not been reused. Bootstrap-intro words (intro_story ≤ 10) are exempt.

### 6.3 Grammar reinforcement

Each newly-introduced grammar point must reappear within the next 5 stories (Check 3.8). The gauntlet's `pedagogical_sanity` step surfaces must-reinforce debts as hard blocks.

### 6.4 Bootstrap ladder (stories 1–10)

Stories 1–10 use a **prescriptive per-story ladder** instead of the steady-state caps. The ladder and must-mint seed words are in `data/v2_5_seed_plan.json`. After story 10 the steady-state rules apply (min 3 new words, max 5; min 1 new grammar, max 1).

## 7. Reader app

### 7.1 Stack

SvelteKit static site (no SSR). Deployed as a PWA with a service worker for full offline support. Source in `src/`; built output in `static/`.

### 7.2 Routes

| Route | Purpose |
|-------|---------|
| `/` | Home / story index |
| `/library` | Story list with progress badges |
| `/read` | Sentence-by-sentence reader with click-to-lookup |
| `/listen` | Audio playback view |
| `/vocab` | Vocabulary index |
| `/grammar` | Grammar point browser |
| `/review` | SRS review queue |
| `/stats` | Learning statistics |

Click-to-lookup popups show kana, romaji, gloss, and grammar tag for any tapped token.

### 7.3 Data loading

The app fetches `static/data/index.json` (story manifest), per-story `static/stories/story_N.json`, `static/data/vocab_state.json`, `static/data/vocab_attributions.json`, `static/data/grammar_state.json`, and `static/data/grammar_attributions.json`. `loadVocabIndex()` and `loadGrammar()` in `src/lib/data/corpus.ts` join the attributions onto the state at fetch time so call sites see a unified view.

### 7.4 Word audio paths

`src/lib/util/word-audio.ts::wordAudioPath(wid)` returns `/audio/words/<wid>.mp3` — the flat layout. Sentence audio is at `/audio/story_N/s<idx>.mp3`.

## 8. Audio pipeline

`pipeline/audio_builder.py` calls Google Cloud TTS (`ja-JP-Standard-A` by default) and writes:

- `audio/story_N/s<idx>.mp3` — one file per sentence
- `audio/words/<wid>.mp3` — one file per vocabulary word (incremental; existing files are reused)

Audio paths are written back into the story JSON. `test_referential_integrity.py` verifies that every sentence and every word in `vocab_state.json` has a corresponding audio file.

## 9. Tests

`pipeline/tests/` runs on every commit via `.githooks/pre-commit` and in CI. All tests must pass on every ship.

| Category | Key tests |
|----------|-----------|
| Schema integrity | `test_schemas.py` — vocab/grammar shape, no orphans |
| Validator correctness | `test_validate_library.py` — every shipped story passes Checks 1–11 |
| Referential integrity | `test_referential_integrity.py` — audio file counts, word-id audio, no obscure kanji surfaces |
| Pedagogical sanity | `test_pedagogical_sanity.py` — `all_words_used` ordering, R1 reinforcement |
| Vocabulary cadence | `test_validate_library.py::test_vocabulary_introduction_cadence` — min 3 new words/story post-bootstrap |
| Grammar cadence | `test_validate_library.py::test_grammar_introduction_cadence` — max 1 new grammar/story post-bootstrap |
| State integrity | `test_state_integrity.py` — no attribution fields on state files, conjunction vocab, mint dedup |
| Attribution sync | `test_state_integrity.py::test_vocab_attribution_manifest_in_sync_with_corpus`, `test_grammar_attribution_manifest_in_sync_with_corpus` |
| Word audio | `test_word_audio_text.py` — word audio file set matches vocab_state |
| Semantic lint | `test_semantic_lint_rules.py` — rules 11.1–11.10 |
| Mint dedup | `test_mint_dedup.py` — same verb across inflections counts as one mint |

**Important:** a dry-run gauntlet green does not guarantee corpus tests green. `test_vocabulary_introduction_cadence`, `test_vocab_words_are_reinforced`, `test_grammar_introduction_cadence`, and `test_audio_word_files_only_for_known_words` are corpus-wide and only fire under `pytest pipeline/tests/`. Always run the full suite after any ship.

## 10. Key invariants

- **`pipeline/inputs/*.bilingual.json` is the only file authors edit.** `stories/*.json` is a derived artifact.
- **The regenerator is idempotent.** Running `regenerate_all_stories.py --apply` twice produces no changes when nothing has been edited.
- **`is_new`, `new_words`, `new_grammar`** are decided by a single library-wide first-occurrence pass inside the regenerator — no heuristics.
- **Attribution fields are never stored on state files.** `vocab_state.json` and `grammar_state.json` carry definition metadata only.
- **Auto-commit after a clean ship.** Per standing user preference: on a clean ship (gauntlet VERDICT: ship, full pytest green), proceed directly to `git add … && git commit … && git push` without asking.
