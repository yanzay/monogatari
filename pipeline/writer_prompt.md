# Monogatari — Story Writer Task

You are writing story **6** for the Monogatari Japanese graded-reader.
Read the authoring rules and plan below, then produce the story JSON.
Output **only** the JSON object — no prose, no markdown fences.

---

## Authoring Rules

# Monogatari — Authoring Rules (Writer Context)

This document is the in-context spec for **Rovo Dev** when authoring `story_raw.json` (stage 2 of the pipeline).
Read it completely before generating. These rules are non-negotiable.

---

## 1. Vocabulary rules

- **Closed set.** You may only use words whose `word_id` is in the allowed set
  (union of `vocab_state.json` words and `plan.json` new_words). No exceptions.
  If you cannot express the intended story with the allowed set, return an error
  object (see Section 6) — do not substitute unlisted words or omit word_ids.

- **Introduce new words naturally.** A new word must appear in a context where
  its meaning is guessable or trivially inferable from context alone — never in
  a position that requires knowing another unseen word to parse the sentence.

- **First occurrence in dictionary form.** The first time a new word appears,
  use its dictionary form when grammatically natural. Inflected introductions
  are allowed only for auxiliary verbs or words that are unnatural in isolation.

- **Repeat new words.** Each new word must appear at least twice in the story.
  Aim to introduce it early (sentence 1–3) and revisit it toward the end
  (sentence 5–8) so the learner encounters it in two different contexts.

- **Prefer concreteness.** When choosing new words, prefer physical and
  observable things (rain, window, tree, cup) over abstract nouns or adverbs.
  Emotionally vivid adjectives (warm, quiet, cold) are welcome at any level.

- **No phantom words.** Do not invent or imply vocabulary that doesn't have a
  word_id in the allowed set. If a particle, auxiliary, or function word is
  needed, it must have an entry in `grammar_state.json` or `plan.new_grammar`.

---

## 2. Grammar rules

- **At most one new grammar point per story.** Zero new grammar is fine — a
  consolidation story that uses only known grammar is valuable.

- **New grammar must appear at least 3 times.** If you introduce a new grammar
  point, use it at least three times across the story so the pattern becomes
  obvious to the learner.

- **No unlisted grammar.** Do not use any grammatical construction whose
  `grammar_id` is not in the allowed set, even if it seems elementary.
  When in doubt, restructure the sentence to use known grammar.

- **Prerequisites respected.** Any grammar point used must have all its
  prerequisites already in `grammar_state.json`.

---

## 3. Content rules

- **Tone:** calm, slice-of-life, age-neutral. The learner is an adult reading
  for comprehension and vocabulary acquisition.

- **Narrative shape:** every story must have a tiny arc — something changes,
  however small. A list of static facts is not a story.
  Good: "It is raining. I drink warm tea. I feel calm."
  Weak: "I wake up. I eat. I go to school." (no emotional beat)

- **Settings that work well at beginner levels:**
  home, kitchen, garden, park, café, train, school, weather, morning/evening
  routines, small emotions (tired, calm, curious, a little lonely, content).

- **Avoid absolutely:**
  - graphic violence or injury
  - sexual content or romantic content beyond platonic warmth
  - politics, religion, elections, governments
  - brand names, real people, celebrities
  - medical or legal advice
  - anything that could be read as instruction for harm
  - drug or alcohol use
  - death or suicide

---

## 4. Output format rules

- Emit **valid JSON only**, matching the `story_N.json` schema exactly.
  No prose, no markdown, no explanation outside the JSON object.

- **Every content token** must have `word_id`.
  Every particle/auxiliary must have `grammar_id`.
  If a content word is inflected (not dictionary form), include an `inflection`
  block with `base` (dictionary kana), `base_r` (if kanji form differs),
  `form` (one of: dictionary, masu, te, ta, nai, negative_past, potential,
  volitional), and `grammar_id` of the relevant grammar point.

- **Furigana:** for every token whose `t` contains kanji, add an `r` field
  with the full kana reading of that token (including okurigana).

- **`is_new: true`** on the first occurrence of each new word.
  **`is_new_grammar: true`** on the first occurrence of each new grammar point.

- **`gloss_en`** must be natural English — how a native speaker would express
  the meaning, not a word-for-word calque. It is for comprehension checking,
  not translation practice. Aim for 1–2 short sentences.

- **Title and subtitle JP fields** must use only words from the allowed vocab
  set and should be tokenised in the same format as sentence tokens.
  English title/subtitle fields are free.

- **`all_words_used`** must list every `word_id` that appears in any token,
  exactly once, in the order first encountered.

- **`checksum`** set to `null` — the pipeline fills this after validation.

---

## 5. Inflection reference

Supported forms: `dictionary`, `masu`, `te` (te_form), `ta`, `nai`,
`negative_past`, `potential`, `volitional`.

| Class    | te-form rule                             | Example          |
|----------|------------------------------------------|------------------|
| Ichidan  | drop る, add て                          | 見る → 見て      |
| Godan く  | drop く, add いて                        | 書く → 書いて    |
| Godan ぐ  | drop ぐ, add いで                        | 泳ぐ → 泳いで    |
| Godan す  | drop す, add して                        | 話す → 話して    |
| Godan つ/る/う | drop, add って                      | 立つ → 立って    |
| Godan ぬ/ぶ/む | drop, add んで                      | 飲む → 飲んで    |
| する     | irregular → して                         |                  |
| 来る     | irregular → 来て (きて)                  |                  |
| 行く     | irregular te → 行って (not 行いて)       |                  |
| i-adj    | drop い, add くて (te), かった (past)    | 寒い → 寒くて    |

The validator will check every inflection block mechanically. Errors result in
rejection and retry.

---

## 6. Engagement & voice (the bar that comes after the validator)

The validator only proves the story is *legal*. The next pipeline stage —
the engagement review (`pipeline/engagement_review.py`) — asks whether
it is **worth reading**. Write with the rubric in mind so you can
approve your own story honestly afterwards.

The rubric scores 1–5 across **hook · voice · originality · coherence ·
closure**. Approval requires **average ≥ 3.5 AND every dimension ≥ 3**.
Full prompt: `pipeline/engagement_review_prompt.md`.

### What the five dimensions actually mean

- **Hook** — does the first sentence drop the reader into a specific,
  sensory moment? `今朝は雨です。` works because it gives time + weather
  in one breath. `私はXです。` doesn't — it's an identification, not an
  observation.
- **Voice** — does a small "I" emerge with consistent tone? Subject-drop
  helps; relentless `私は…` flattens the narrator into a worksheet.
- **Originality** — within the brutally narrow vocabulary, can you find
  one small surprise? A fresh juxtaposition (`雨は静かです`), an
  unexpected pairing (`卵とお茶`), a personification of weather. Aim for
  one such moment per story.
- **Coherence** — does each sentence pull forward from the last? A list
  of independent flashcards reads as a worksheet. Even a 6-sentence
  story should have a tiny arc: setup → small turn → small landing.
- **Closure** — does the last line linger? End on an image or a felt
  observation, not a flat statement. The strongest closers in the
  current library tie two motifs from earlier in the story into one
  line.

### Positive examples (from stories already shipped)

The four shipped stories all pass the bar. Lean on these patterns.

**Hooks that work:**

```
夕方、私と友達は公園を歩きます。       (story 2 — time-comma + companion + verb)
夕方、私は友達と公園を歩きます。       (story 4 — same pattern, slightly different framing)
今朝は雨です。                          (story 1 — minimal time + weather)
朝、雨です。                            (story 3 — four-syllable sensory poem)
```

The pattern that recurs: **time-of-day → comma → concrete observation
or action**. The comma after the time word does a lot of work — it
slows the line down and makes the rest land as observation rather
than identification.

**Closers that work:**

```
雨と夕方と公園を歩きます。              (story 2 — return to opening verb with three motifs as object)
雨の外と静かな朝、いい気分です。        (story 3 — weather + time + feeling in one line)
散歩と友達はいい気分です。              (story 4 — pulls two motifs into one felt observation)
今朝はいい気分です。                    (story 1 — symmetry with opener; small but earned)
```

The pattern that recurs: **named motifs from the body, then a single
short evaluation**. The closer is not the place to introduce a new
image — it's where the existing images settle.

### Anti-patterns (what to avoid)

These pulled past stories under the bar and forced revisions:

- **Particle as decoration.** `気分もいいです` ends a story by
  attaching `も` to a feeling that was never set up — the particle
  decorates instead of meaning. Anchor `も` to a real reciprocity
  (`友達もお茶を飲みます。`).
- **Refrain becomes a tic.** Repeating the same evaluative adjective
  (`静か`) more than twice in a 7-sentence story stops being
  observation and becomes verbal wallpaper.
- **Inconsistent claims.** Saying "warm at evening" / "warm outside"
  reads as careless. Anchor temperature claims to a thing (the tea,
  the eggs), not the air.
- **Definition as opener.** `XはYとZです` is a useful sentence but a
  weak hook. If you want the definition, place it second; lead with
  a sensory beat.
- **Gloss inflation.** Don't write `gloss_en` "After that, I eat my
  breakfast." if the JP has no それから. Glosses must reflect what is
  actually in the JP.
- **Subject-grind.** Five `私は…` openers in a row. Drop the subject
  when context allows — Japanese is generous about this and the
  narrator immediately sounds less like a worksheet.

---

## 7. When to refuse

If the constraints cannot be satisfied — vocabulary too sparse, planned new
words incoherent, grammar prerequisites missing — return this object and stop:

```json
{
  "error": "cannot_generate",
  "reason": "<one sentence explaining why>",
  "missing_vocab": ["word or concept you needed but lacked"],
  "missing_grammar": ["grammar pattern you needed but lacked"]
}
```

Do not attempt to generate a partial or approximate story.
A clean refusal is better than a story that fails validation.


---

## Plan

```json
{
  "story_id": 6,
  "title_jp": "猫",
  "title_en": "The Cat",
  "subtitle_jp": "雨の窓",
  "subtitle_en": "The rainy window",
  "theme": "A small surprise — a cat appears at the rainy window. The narrator's quiet morning gains a second presence; the closer pulls cat + narrator into one observation.",
  "setting": "A rainy morning at home. The narrator looks out a window; a cat is suddenly there in the rain, then stays — a quiet reciprocal moment between two presences.",
  "constraints": {
    "must_reuse_words": [
      "W00002",
      "W00004",
      "W00006",
      "W00011",
      "W00015"
    ],
    "forbidden_words": [],
    "avoid_topics": [
      "violence",
      "romance",
      "politics"
    ]
  },
  "target_word_count": 24,
  "max_sentences": 7,
  "new_words": [
    "W00028",
    "W00029"
  ],
  "new_word_definitions": {
    "W00028": {
      "id": "W00028",
      "surface": "猫",
      "kana": "ねこ",
      "reading": "neko",
      "pos": "noun",
      "meanings": [
        "cat"
      ],
      "first_story": 6
    },
    "W00029": {
      "id": "W00029",
      "surface": "います",
      "kana": "います",
      "reading": "imasu",
      "pos": "verb",
      "verb_class": "ichidan",
      "meanings": [
        "to be (animate); to exist (animate)"
      ],
      "first_story": 6
    }
  },
  "new_grammar": [],
  "new_grammar_definitions": {},
  "context_words_to_reuse": [
    "W00002",
    "W00004",
    "W00005",
    "W00006",
    "W00011",
    "W00013",
    "W00015",
    "W00016"
  ],
  "notes": "Hook follows the proven 'time-of-day, comma, weather' pattern (story 5 / story 1). Sentence 2 is the turn line: そして anchors chronology in the JP, が presents the cat as new information (textbook use of が vs. は; G002_ga_subject was introduced in story 1 but barely used since — story 6 cements it). Sentence 4 reuses が for 'in the rainy window, a cat is there' — second pass on the new-information construction. Sentence 5 is the reciprocal moment (cat looks at me) — the small specific gesture the engagement rules ask for. Closer follows the 'A and B, feeling' pattern (stories 4, 5). No new grammar — the engagement budget goes to the cat as the surprise."
}
```

---

## Allowed vocabulary (ALL words you may use — no others)

- `W00001`: **今朝** (けさ) [noun] — this morning [occ:2]
- `W00002`: **雨** (あめ) [noun] — rain [occ:3]
- `W00003`: **私** (わたし) [pronoun] — I, me [occ:7]
- `W00004`: **窓** (まど) [noun] — window [occ:2]
- `W00005`: **外** (そと) [noun] — outside [occ:4]
- `W00006`: **見ます** (みます) [verb] — to see, to look [occ:6]
- `W00007`: **木** (き) [noun] — tree [occ:5]
- `W00008`: **濡れる** (ぬれる) [verb] — to get wet [occ:1]
- `W00009`: **お茶** (おちゃ) [noun] — tea, green tea [occ:5]
- `W00010`: **飲みます** (のみます) [verb] — to drink [occ:3]
- `W00011`: **静か** (しずか) [adjective] — quiet, calm [occ:6]
- `W00012`: **温かい** (あたたかい) [adjective] — warm [occ:5]
- `W00013`: **いい** (いい) [adjective] — good, nice [occ:6]
- `W00014`: **気分** (きぶん) [noun] — feeling, mood [occ:5]
- `W00015`: **朝** (あさ) [noun] — morning [occ:3]
- `W00016`: **公園** (こうえん) [noun] — park [occ:4]
- `W00017`: **歩きます** (あるきます) [verb] — to walk [occ:4]
- `W00018`: **夕方** (ゆうがた) [noun] — evening, late afternoon [occ:3]
- `W00019`: **朝ごはん** (あさごはん) [noun] — breakfast [occ:1]
- `W00020`: **食べます** (たべます) [verb] — to eat [occ:1]
- `W00021`: **卵** (たまご) [noun] — egg [occ:1]
- `W00022`: **友達** (ともだち) [noun] — friend [occ:2]
- `W00023`: **散歩** (さんぽ) [noun] — walk, stroll [occ:2]
- `W00024`: **花** (はな) [noun] — flower [occ:3]
- `W00025`: **ドア** (ドア) [noun] — door [occ:1]
- `W00026`: **帰ります** (かえります) [verb] — to return home, to go back [occ:1]
- `W00027`: **風** (かぜ) [noun] — wind [occ:1]
- `W00028`: **猫** (ねこ) [noun] — cat **[NEW]**
- `W00029`: **います** (います) [verb] — to be (animate); to exist (animate) **[NEW]**

---

## Allowed grammar (ALL grammar_ids you may use — no others)

- `G001_wa_topic`: は — topic marker — Marks the topic of the sentence. Pronounced 'wa', not 'ha'.
- `G002_ga_subject`: が — subject marker — Marks the grammatical subject of the sentence.
- `G003_desu`: です — polite copula — Polite form of 'to be'. Links a topic to a description.
- `G004_ni_location`: に — location / direction marker — Marks the location of existence or the direction of movement.
- `G005_wo_object`: を — direct object marker — Marks the direct object of a verb.
- `G006_kara_from`: から — from — Marks a starting point in space, time, or reason.
- `G007_te_form`: て-form — connective verb form — Connects clauses or acts as a base for compound forms like て-います.
- `G008_te_iru`: 〜ています — ongoing state / action in progress — Expresses an action in progress or a resulting state.
- `G009_mo_also`: も — also / too — Marks something as additional. Replaces は or が when 'X too / X also' is meant.
- `G010_to_and`: と — and (exhaustive list) — Connects two or more nouns into a complete list ('A and B').
- `G011_ya_partial`: や — and (partial / non-exhaustive list) — Lists nouns as a non-exhaustive 'A, B, and so on'.
- `G012_soshite_then`: そして — and then — Sentence-initial connector meaning 'and then', linking sequential clauses.

---

## New word definitions (introduce these in the story)

- `W00028`: **猫** (ねこ) [noun] — cat
- `W00029`: **います** (います) [verb · ichidan] — to be (animate); to exist (animate)

---

## Output schema

Produce a `story_6.json` object with this structure:

```json
{
  "story_id": 6,
  "title": {
    "jp": "<kanji/kana title>",
    "en": "<English title>",
    "tokens": [
      {"t": "<kanji>", "r": "<kana>", "word_id": "<id>", "role": "content"}
    ]
  },
  "subtitle": {
    "jp": "<subtitle>",
    "en": "<English subtitle>",
    "tokens": [ ... ]
  },
  "plan_ref": "plan.json",
  "new_words": ["W00028", "W00029"],
  "new_grammar": [],
  "all_words_used": ["<every word_id used, in order of first appearance>"],
  "sentences": [
    {
      "idx": 0,
      "tokens": [
        {"t": "<kanji>", "r": "<kana reading>", "word_id": "<id>", "role": "content", "is_new": true},
        {"t": "<particle>", "grammar_id": "<gid>", "role": "particle"},
        {"t": "<inflected>", "r": "<kana>", "word_id": "<id>", "role": "content",
          "inflection": {"base": "<dict-kanji>", "base_r": "<dict-kana>", "form": "te_form", "grammar_id": "<gid>"}},
        {"t": "。", "role": "punct"}
      ],
      "gloss_en": "<natural English>",
      "audio": null
    }
  ],
  "word_audio": {},
  "checksum": null
}
```

### Rules reminder
- Every `role: content` token needs `word_id`
- Every `role: particle` or `role: aux` token needs `grammar_id`
- Every token whose `t` contains kanji needs `r` (full kana reading)
- Inflected forms need an `inflection` block
- `is_new: true` on first occurrence of each new word
- `is_new_grammar: true` on first occurrence of each new grammar point
- 5–8 sentences
- Each new word appears at least twice
- New grammar appears at least 3 times (if introduced)

If you cannot satisfy the constraints, output:
```json
{"error": "cannot_generate", "reason": "...", "missing_vocab": [], "missing_grammar": []}
```
