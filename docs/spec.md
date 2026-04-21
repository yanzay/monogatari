# Monogatari — System Specification

A graded-reader application for learning Japanese through Rovo-Dev-authored short stories, with guaranteed vocabulary control, click-to-lookup reading, and an integrated SRS reviewer.

**Version 0.1** · Target reader: one developer · Author: Rovo Dev (in-conversation)

## 1. Goals and non-goals

### 1.1 Goals

- Learner reads one short story per session. Each story is fully comprehensible given prior stories plus 3–5 new words introduced in this one.
- Every word is clickable and returns a dictionary entry + the grammar note attached to its first occurrence.
- Vocabulary growth is deterministic and auditable: the system can prove exactly which words the learner has been exposed to and how many times.
- New words from each story enter an SRS queue. Review happens inside the same app, in-context (the word is shown inside the sentence it first appeared in).
- Stories are reproducible: given the same vocab state and seed, the generation prompt must produce the same class of story (not necessarily byte-identical, but within the same vocabulary envelope).
- Audio (sentence-level and word-level) can be generated from the same authoring output without a second human pass.

### 1.2 Non-goals (v1)

- Production-grade morphological tokenization (we use pre-tokenized authored output; learner never types free Japanese).
- Handwriting / output production by the learner.
- Pitch-accent teaching (we store pitch but don't drill it).
- Kanji-writing practice.
- Multi-user accounts, sync, social features.
- Generating stories client-side at runtime. Generation is an offline authoring pipeline; the app only reads pre-built story JSON.

### 1.3 Explicit design bets

- **Pre-tokenized, not runtime-tokenized.** Rovo Dev emits tokens already segmented and linked to dictionary IDs. The reader never tokenizes. This avoids kuromoji/sudachi in the browser and makes rendering trivial.
- **Vocabulary is a closed set per story.** The generator cannot invent words; it picks from an allowed list the pipeline constructs.
- **Grammar is tracked as discrete IDs, not inferred.** Each grammar point (e.g. `G001_wa_topic`, `G014_te_form`) is introduced explicitly, with a note displayed on its first appearance.
- **The learner's SRS is fully self-contained.** Progress lives in the browser's localStorage; there is no integration with external SRS systems.

## 2. System architecture

```text
┌──────────────────────────────────────────────────────────────┐
│  AUTHORING PIPELINE (offline, run by developer)              │
│                                                              │
│  vocab_state.json ──┐                                        │
│                     ├──► 1. STORY PLANNER (Rovo Dev)        │
│  grammar_state.json ┤        emits: plan.json                │
│                     │                                        │
│  authoring_rules.md ┘                                        │
│                               │                              │
│                               ▼                              │
│                      2. STORY WRITER (Rovo Dev)             │
│                         emits: story_raw.json                │
│                               │                              │
│                               ▼                              │
│                      3. VALIDATOR (deterministic code)       │
│                         pass → story_N.json                  │
│                         fail → regenerate (max 3 tries)      │
│                               │                              │
│                               ▼                              │
│                      4. AUDIO BUILDER                        │
│                         TTS per sentence + per new word      │
│                         emits: audio/story_N/*.mp3           │
│                               │                              │
│                               ▼                              │
│                      5. STATE UPDATER                        │
│                         writes new vocab_state, grammar_state│
└──────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────┐
│  READER APP (static web, runs in browser)                    │
│                                                              │
│  Loads: stories/story_N.json + audio/story_N/*.mp3           │
│  Stores (localStorage): learner_state.json                   │
│                                                              │
│  Views:  Read  │  Review (SRS)  │  Vocab  │  Grammar         │
└──────────────────────────────────────────────────────────────┘
```

The authoring pipeline runs on the developer's machine whenever a new story is needed. The reader app is a static bundle that consumes its output.

## 3. Data model

All files are JSON except `authoring_rules.md` (prompt context) and audio (mp3).

### 3.1 `vocab_state.json`

The authoritative list of words the learner has been exposed to. Updated only by the State Updater after a story is validated and shipped.

```json
{
  "version": 1,
  "updated_at": "2026-04-21T12:00:00Z",
  "last_story_id": 12,
  "words": {
    "W00042": {
      "id": "W00042",
      "surface": "食べる",
      "kana": "たべる",
      "reading": "taberu",
      "pos": "verb",
      "verb_class": "ichidan",
      "meanings": ["to eat"],
      "first_story": 4,
      "occurrences": 7,
      "last_seen_story": 11,
      "grammar_tags": ["G003_ru_verb"],
      "jmdict_id": 1358280
    }
  }
}
```

**Notes:**

- `id` is a stable internal ID (`W` + zero-padded number, assigned on first introduction).
- `surface` is the form that appears in stories (e.g. 食べる, dictionary form). Inflected forms are handled via grammar points, not as separate vocab entries.
- `jmdict_id` lets us cross-reference JMdict for richer lookups without shipping the whole dictionary inline.
- `occurrences` is a simple counter for "how often has the learner seen this".

### 3.2 `grammar_state.json`

```json
{
  "version": 1,
  "points": {
    "G001_wa_topic": {
      "id": "G001_wa_topic",
      "title": "は — topic marker",
      "short": "Marks the topic of the sentence. Often translatable as 'as for X'. Pronounced 'wa', not 'ha'.",
      "long": "The topic particle は signals what the sentence is ABOUT. It's distinct from the subject marker が...",
      "genki_ref": "L1",
      "first_story": 1,
      "prerequisites": []
    }
  }
}
```

Grammar points have prerequisites. The Planner cannot introduce a grammar point whose prerequisites aren't already in `grammar_state.json`.

### 3.3 `plan.json` (ephemeral, step 1 → step 2)

```json
{
  "story_id": 13,
  "target_word_count": 55,
  "max_sentences": 8,
  "new_words": ["W00231", "W00232", "W00233"],
  "new_grammar": ["G017_te_iru"],
  "theme": "morning routine",
  "setting": "A student gets ready for school",
  "constraints": {
    "must_reuse_words": ["W00042", "W00089"],
    "forbidden_words": [],
    "avoid_topics": ["violence", "romance", "politics"]
  },
  "seed": 847362
}
```

The Planner produces this from vocab/grammar state + a "difficulty step" policy. It is human-inspectable before generation proceeds.

### 3.4 `story_N.json` (shipped artifact)

This is the contract between authoring and the reader app. Validator checks every field.

```json
{
  "story_id": 13,
  "title": { "jp": "あさ", "en": "Morning" },
  "subtitle": { "jp": "あたらしいいちにち", "en": "A new day" },
  "plan_ref": "plan_013.json",
  "new_words": ["W00231", "W00232", "W00233"],
  "new_grammar": ["G017_te_iru"],
  "all_words_used": ["W00001", "W00042", "..."],
  "sentences": [
    {
      "idx": 0,
      "tokens": [
        { "t": "わたし", "word_id": "W00001", "role": "content" },
        { "t": "は",     "grammar_id": "G001_wa_topic", "role": "particle" },
        { "t": "あさ",   "word_id": "W00231", "role": "content", "is_new": true },
        { "t": "、",     "role": "punct" },
        { "t": "はを",   "word_id": "W00148", "role": "content" },
        { "t": "みがいて", "word_id": "W00232", "role": "content", "is_new": true,
          "inflection": { "base": "みがく", "form": "te_form", "grammar_id": "G014_te_form" } },
        { "t": "います",  "grammar_id": "G017_te_iru", "role": "aux", "is_new_grammar": true },
        { "t": "。",     "role": "punct" }
      ],
      "gloss_en": "As for me, in the morning, I'm brushing my teeth.",
      "audio": "audio/story_013/s0.mp3"
    }
  ],
  "word_audio": {
    "W00231": "audio/story_013/w_W00231.mp3",
    "W00232": "audio/story_013/w_W00232.mp3",
    "W00233": "audio/story_013/w_W00233.mp3"
  },
  "checksum": "sha256:abc123..."
}
```

**Token roles:** `content` (noun/verb/adj/adv), `particle`, `aux` (auxiliary verb / grammatical ending), `punct`.

**Inflection block:** optional. When present, it tells the reader "this token is the te_form of みがく, which is word W00232." This is how we avoid duplicating every conjugated form as a separate dictionary entry.

### 3.5 `learner_state.json` (browser localStorage)

```json
{
  "version": 1,
  "current_story": 13,
  "last_opened": "2026-04-21T08:00:00Z",
  "srs": {
    "W00001": {
      "word_id": "W00001",
      "first_learned_story": 1,
      "context_story": 1,
      "context_sentence_idx": 0,
      "interval_days": 7,
      "ease": 2.5,
      "reps": 4,
      "lapses": 0,
      "due": "2026-04-28T00:00:00Z",
      "status": "learning"
    }
  },
  "story_progress": {
    "13": { "reached_sentence": 4, "completed": false }
  },
  "prefs": {
    "show_gloss_by_default": false,
    "show_furigana": "on_kanji",
    "audio_autoplay": false
  }
}
```

**Status values:** `new` (not yet reviewed), `learning` (in first 3 reps), `young` (interval < 21d), `mature` (interval ≥ 21d), `leech` (lapses ≥ 6).

## 4. The authoring pipeline in detail

### 4.1 Stage 1 — Story Planner (Rovo Dev)

**Input:** `vocab_state.json`, `grammar_state.json`, `authoring_rules.md`, a difficulty step config.

**Output:** `plan.json`.

**Prompt skeleton (handed to Rovo Dev):**

```text
You are the planner for a Japanese graded-reader system. Your job is to
decide WHAT the next story should contain, not to write it.

Here is the learner's current state:
<vocab_state>{{ JSON }}</vocab_state>
<grammar_state>{{ JSON }}</grammar_state>

Difficulty policy for this story:
- Introduce exactly {{N_NEW_WORDS}} new words (here: 3).
- Optionally introduce at most 1 new grammar point.
- Story length: 5–8 sentences, 35–65 content tokens total.
- At least 60% of content tokens must be previously-seen words
  whose occurrence count is < 5 (prioritize reinforcing weak vocab).

Constraints (hard):
- New grammar prerequisites must all exist in grammar_state.
- Avoid topics: violence, graphic content, politics, romance beyond friendship.
- New words must be i+1: high-frequency, concrete, and combinable with
  existing vocab without needing additional unseen words to make sense.

Produce plan.json. Explain your word choices in a "rationale" field
(will not be shown to learner).
```

**Determinism:** the Planner is seeded. We log its output and the developer can edit `plan.json` by hand before proceeding.

### 4.2 Stage 2 — Story Writer (Rovo Dev)

**Input:** `plan.json`, `vocab_state.json`, `grammar_state.json`, `authoring_rules.md`.

**Output:** `story_raw.json` in the `story_N.json` schema.

**Key instruction to the Writer:**

```text
You may only use words whose word_id is in this set: {{ALLOWED_IDS}}.
This set is the union of (a) all words in vocab_state.json and (b) the new words from plan.json. If you need a word not in this set, stop and return an error object instead of the story.
You must emit tokens pre-segmented. For every content word token, you must supply its word_id. For every particle or auxiliary, you must supply its grammar_id. If a word is inflected (not dictionary form), supply the inflection block.
```

The Writer is given the full `authoring_rules.md` (see Section 5).

### 4.3 Stage 3 — Validator (deterministic)

This is code, not Rovo Dev. It is the guardrail that makes the whole system trustworthy.

**Checks performed on `story_raw.json`:**

1. **Schema validity.** All required fields present, types correct.
2. **Closed vocabulary.** For every token with `role: content`:
   - `word_id` exists in `vocab_state.json` OR in `plan.json.new_words`.
   - If `inflection.base` is present, it resolves to a known word.
3. **Closed grammar.** Every `grammar_id` exists in `grammar_state.json` OR in `plan.json.new_grammar`.
4. **Budget.** Exactly the planned new words appear, each at least once. No extra new words. At most the planned new grammar.
5. **Surface ↔ ID consistency.** The `t` (surface text) matches the dictionary surface for the referenced word, OR the inflection block correctly derives it (we apply a small deterministic conjugation check for ichidan, godan, and irregular verbs + i-adjectives; see Section 6).
6. **Reuse quota.** ≥ 60% of content tokens reference words with occurrences < 5 in current state (reinforcement check).
7. **Length.** Sentence count 5–8, total content tokens in target range.
8. **No forbidden topics.** A keyword heuristic flags the `gloss_en` for disallowed content (violence, romance, politics, etc.).
9. **Gloss sanity.** The English gloss is non-empty and roughly as long as expected (heuristic: 0.8×–3.0× token count in words).
10. **Round-trip.** Re-joining all `t` values should produce a clean Japanese sentence (no double spaces, no stray fragments).

**Failure policy:** If validation fails, the pipeline feeds the errors back to the Writer (max 3 retry cycles). If still failing, the pipeline stops and the developer is notified with the diagnostic JSON.

### 4.4 Stage 4 — Audio Builder

For each sentence, synthesize one MP3. For each new word, synthesize a clean word-in-isolation MP3. Use a TTS with SSML to:

- Slow the sentence audio to ~0.85× natural speed by default (configurable).
- Emit word audio without SSML modifications (natural speed, dictionary form).

**Recommended providers** (any works; keep provider abstracted behind an interface):

- Google Cloud TTS (voice ja-JP-Neural2-B or similar)
- Azure Speech (voice ja-JP-NanamiNeural)
- ElevenLabs (more natural, paid)

Audio files are named deterministically: `s{idx}.mp3` for sentences, `w_{word_id}.mp3` for words.

### 4.5 Stage 5 — State Updater

**Pure function.** Reads `story_N.json` (post-validation) and current state, produces new state:

- Adds new words to `vocab_state.words` with `first_story: N`.
- Increments `occurrences` and updates `last_seen_story` for every word referenced.
- Adds new grammar points.
- Updates `last_story_id`.

Writes atomically. Keeps a dated backup of the previous state in `/state_backups/`.

## 5. Authoring rules (`authoring_rules.md`)

This is the document handed to Rovo Dev in-context for stage 2 (Story Writer). It is also the style bible the developer reviews. The rules below are what must be in it.

### 5.1 Vocabulary rules

- **Closed set.** Use only words whose ID is in the allowed set. No exceptions. If you cannot express an idea with the allowed set, return an error object; do not substitute.
- **Introduce new words naturally.** A new word should appear in a context where its meaning is guessable or trivially inferable — never in a position that requires knowing another unseen word to parse.
- **First occurrence** of a new word should be in its dictionary form when possible. Inflected-only introductions are allowed only for auxiliary verbs or words whose dictionary form is unnatural (rare).
- **Repeat new words.** Each new word should appear at least twice in the story. Ideally, each new word appears early and then once more toward the end.
- **Prefer concreteness.** A new word should be physical, observable, or emotionally vivid before abstract.

### 5.2 Grammar rules

- At most one new grammar point per story. Zero is fine (consolidation story).
- The new grammar point must appear at least 3 times across the story so the pattern is obvious.
- If no new grammar is introduced, every grammar construction in the story must already be in `grammar_state.json`.
- Do not use a grammar form whose ID is not in the allowed set, even if it "looks simple".

### 5.3 Content rules

- **Tone:** calm, slice-of-life, age-neutral. The learner is an adult reading for comprehension.
- **Avoid:** graphic violence, sexual content, politics, religion, brand names, real people, medical/legal advice, anything that could be read as instruction for harm.
- **Settings** that work well at beginner levels: home, school, train, park, café, kitchen, weather, routines, small emotions (tired, curious, happy, a little lonely).
- A story should have a tiny narrative shape: something changes, however small. Not just a list of facts. "I wake up. I brush my teeth. I go to school." is weaker than "I wake up. It is raining. I drink warm tea and feel better."

### 5.4 Output format rules

- Emit valid JSON matching the `story_N.json` schema exactly. No prose outside JSON.
- Every content token gets `word_id`. Every particle/aux gets `grammar_id`. Every inflected form gets an inflection block with `base` and `form`.
- `gloss_en` is natural English, not word-for-word. It is for comprehension checking, not translation practice.
- **Title and subtitle:** short, evocative, use only allowed vocab for the JP versions. English versions are free.

### 5.5 When to refuse

Return this object and stop:

```json
{
  "error": "cannot_generate",
  "reason": "<short explanation>",
  "missing_vocab": ["suggested word 1", "..."],
  "missing_grammar": ["suggested grammar 1"]
}
```

Valid reasons include: allowed vocabulary too sparse to tell a coherent story; planned new words are mutually incoherent; grammar prerequisite missing.

## 6. Inflection verification (Section 4.3, check #5)

The Validator needs to check that みがいて is really the te-form of みがく. We keep a small deterministic conjugation table rather than a full morphological analyzer.

**Forms supported in v1:** dictionary, masu, te, ta, nai, negative_past, potential, volitional.

**Rules encoded per verb class:**

- **Ichidan:** stem = surface − る. te = stem + て, ta = stem + た, etc.
- **Godan:** final-kana shift tables (く→いて, ぐ→いで, す→して, つ/る/う→って, ぬ/ぶ/む→んで, etc.)
- **Irregular:** する, 来る, 行く (いく→いって special case) listed explicitly.
- **I-adjective:** -い → -く (adv), -くて (te), -かった (past), -くない (neg).

Validator takes `inflection.base`, `inflection.form`, and the surface `t`; recomputes the expected surface; rejects if mismatch.

This is strict enough to catch authoring fabrications without requiring heavy NLP.

## 7. Reader app spec

### 7.1 Stack

- Single-page static site. No backend.
- Vanilla JS or a minimal framework (Preact, Solid). No build step preferred; if one is used, output must be static.
- **Fonts:** Shippori Mincho (JP), Fraunces (EN), JetBrains Mono (labels).
- **Styling:** CSS variables, hand-tuned.
- **Data:** fetch `stories/story_{N}.json` on demand. Cache in IndexedDB for offline.
- **Audio:** one `<audio>` element per sentence, constructed lazily.

### 7.2 Views

**Read view**

- Shows current story. Title, subtitle, ornament, then sentences.
- Each sentence: Japanese (large serif) + play button + optional English gloss (toggle).
- Each content token is clickable. Underline style: solid red for first-in-story, dotted grey for seen-before, nothing for particles unless clicked.
- Click → bottom-sheet popup with: word, reading (kana + romaji), POS tag, meaning, grammar note if applicable, first-seen info, SRS status dot.
- Controls: prev/next story (next disabled if current not completed past last sentence), progress dots per sentence.
- "New words" panel at bottom of the story: chips for each new word.

**Review view**

- Pulls due items from `learner_state.srs`. Shows the word inside its original context sentence (with the target word highlighted).
- Reveal button shows reading + meaning + gloss of that sentence.
- Four grade buttons: Again (0), Hard (1), Good (2), Easy (3). SRS scheduler (Section 7.4) updates the card.
- Shows review-queue counter in the nav bar.
- If nothing due: "Nothing due. Read the next story or come back later."

**Vocab view**

- Stats: total words seen, learning, young, mature.
- Scrollable list of all known words. Each row: JP surface, reading, meaning, status dot, first-story chip. Click → popup.
- Filter: by status, by story, by search.

**Grammar view**

- List of grammar points in order introduced. Each expandable to show the long note and the sentences in which it has appeared.

### 7.3 Interactions and rendering rules

- **Furigana.** Preference: `off` / `on_kanji` / `all`. When `on_kanji`, any token containing a kanji shows ruby above. Data comes from the `kana` field of the word entry.
- Clicking a particle/aux opens a grammar popup instead of a dictionary popup.
- **Sentence audio autoplay:** off by default. When on, plays the current sentence, then auto-advances (with a settable delay).
- **Mobile:** tap behavior identical. Popup becomes a bottom sheet.

### 7.4 SRS scheduler

Simple, SM-2 inspired, runs entirely client-side.

- New card after first exposure: interval 0, ease 2.5, status = `new`
- **On grade:**
  - **again (0):** reps = 0, interval = 10 minutes, ease -= 0.20 (floor 1.3), lapses += 1
  - **hard (1):** interval = max(1, round(interval × 1.2)), ease -= 0.15 (floor 1.3)
  - **good (2):** if reps == 0: interval = 1 day; elif reps == 1: interval = 3 days; else: interval = round(interval × ease); reps += 1
  - **easy (3):** same as good, then interval = round(interval × 1.3), ease += 0.10
- **Status transitions:**
  - interval < 1d → learning
  - 1d ≤ interval < 21d → young
  - interval ≥ 21d → mature
  - lapses ≥ 6 → leech (flagged for user)

New words enter the SRS the first time the user finishes a sentence containing them (or explicitly clicks "mark new words as learned" at the end of a story — TBD which trigger feels better; ship with end-of-story trigger, A/B later).

### 7.5 Offline and persistence

- `learner_state.json` written to localStorage on every change, debounced 500ms.
- Story JSONs and audio cached via Service Worker once fetched.
- **Export/import:** a button in settings dumps the full learner state as JSON so the learner can back up / move devices.

## 8. Milestone plan

- **M1** — Manual story 1 + reader skeleton. No pipeline. Hand-author story 1 in the JSON schema. Build the Read view and popup. Confirm the schema feels right in practice.
- **M2** — SRS reviewer + Vocab view. Add the review loop and the vocab list. Ship to yourself. Use it daily for a week.
- **M3** — Validator. Write and test the deterministic validator against hand-authored stories and deliberately-broken stories. This is the keystone.
- **M4** — Writer prompt + Planner prompt. Once the validator is trustworthy, wire up the Rovo Dev authoring stages. Generate stories 2–5 under close review.
- **M5** — Audio. Add TTS stage. Integrate playback in the reader.
- **M6** — Grammar view + polish. Quality-of-life.
- **M7** — Offline support. Service worker caches app shell, stories, and audio so the reader works fully offline once a story has been opened.

Ship M1–M2 before touching the authoring pipeline. The reader has to be good first, or no amount of generation quality helps.

## 9. Open questions

- **Kanji introduction policy.** Kana-only for the first N stories, then gradually introduce kanji for high-frequency words? Or kanji from day one with furigana? Tentative: kana-only for stories 1–5, then kanji-with-furigana, with a "hide furigana on known kanji" toggle later.
- **Trigger for SRS entry.** End-of-story vs per-sentence. Lean end-of-story; revisit after two weeks of use.
- **Difficulty ramping.** Fixed "3 new words per story" forever, or gradually increase to 5–7 as vocab grows? Probably ramp, with a hard ceiling based on ratio of new-to-known (e.g. never more than 8% new tokens in a story).
- **How to surface weak vocab for reinforcement.** Right now the planner is told "prioritize words with occurrences < 5." Better signal may come from SRS (words with recent lapses). Merge the two eventually.
- **Pitch accent.** Store now, drill later? Probably yes — store in the dictionary entry from the start so we don't migrate later.

## 10. What this spec does not pin down

- The exact prompts handed to Rovo Dev at each stage (the in-repo prompt files are the canonical version; this spec only describes their intent).
- The exact prompt text (skeletons given; iteration expected).
- UI copy, colors beyond the current palette, and animation timing.
- TTS voice choice.

These are implementation details and can change without spec changes.

*End of spec.*
