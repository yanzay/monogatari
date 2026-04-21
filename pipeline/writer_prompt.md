# Monogatari — Story Writer Task

You are writing story **4** for the Monogatari Japanese graded-reader.
Read the authoring rules and plan below, then produce the story JSON.
Output **only** the JSON object — no prose, no markdown fences.

---

## Authoring Rules

# Monogatari — Authoring Rules (Writer Context)

This document is the in-context brief for **Rovo Dev** when authoring `story_raw.json` (stage 2 of the pipeline).
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

## 6. When to refuse

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
  "story_id": 4,
  "target_word_count": 24,
  "max_sentences": 8,
  "new_words": [
    "W00022",
    "W00023",
    "W00024"
  ],
  "new_grammar": [
    "G011_ya_partial"
  ],
  "theme": "evening park walk with a friend",
  "setting": "An unhurried walk through the local park at dusk; the narrator and a friend pause to look at trees and flowers, then warm up with tea.",
  "constraints": {
    "must_reuse_words": [
      "W00007",
      "W00009",
      "W00010",
      "W00011",
      "W00012",
      "W00016",
      "W00017",
      "W00018"
    ],
    "forbidden_words": [],
    "avoid_topics": [
      "violence",
      "romance",
      "politics"
    ]
  },
  "new_word_definitions": {
    "W00022": {
      "surface": "友達",
      "kana": "ともだち",
      "reading": "tomodachi",
      "pos": "noun",
      "verb_class": null,
      "adj_class": null,
      "meanings": [
        "friend"
      ],
      "grammar_tags": []
    },
    "W00023": {
      "surface": "散歩",
      "kana": "さんぽ",
      "reading": "sanpo",
      "pos": "noun",
      "verb_class": null,
      "adj_class": null,
      "meanings": [
        "walk",
        "stroll"
      ],
      "grammar_tags": []
    },
    "W00024": {
      "surface": "木",
      "kana": "き",
      "reading": "ki",
      "pos": "noun",
      "verb_class": null,
      "adj_class": null,
      "meanings": [
        "tree"
      ],
      "grammar_tags": []
    }
  },
  "new_grammar_definitions": {
    "G011_ya_partial": {
      "title": "や — and (partial / non-exhaustive list)",
      "short": "Lists nouns as a non-exhaustive 'A, B, and so on'.",
      "long": "The particle や connects nouns in a non-exhaustive list, implying 'and others'. 'AやB' means 'A, B, and similar things'. Distinct from と (exhaustive 'and only'). Often closed with 'など' for emphasis. Comes between nouns; not used between verbs or full clauses.",
      "genki_ref": "L8",
      "prerequisites": [
        "G010_to_and"
      ]
    }
  },
  "rationale": "Story 4 keeps the cozy domestic register and pivots from indoor scenes (stories 1–3) to a quiet outdoor walk. It introduces a small social-life cluster (友達, 散歩) plus 木 to set up future nature-themed stories. や is a natural fit for listing things observed in a park (trees, flowers, etc.), and contrasts cleanly with the previously-introduced と (exhaustive 'and'). Heavy reuse of weak vocab (花, お茶, 温かい, 静か, 公園, 夕方) targets the planner's 'occurrences < 5' priority list.",
  "seed": 40422
}
```

---

## Allowed vocabulary (ALL words you may use — no others)

- `W00001`: **今朝** (けさ) [noun] — this morning [occ:2]
- `W00002`: **雨** (あめ) [noun] — rain [occ:2]
- `W00003`: **私** (わたし) [pronoun] — I, me [occ:4]
- `W00004`: **窓** (まど) [noun] — window [occ:2]
- `W00005`: **外** (そと) [noun] — outside [occ:3]
- `W00006`: **見ます** (みます) [verb] — to see, to look [occ:3]
- `W00007`: **木** (き) [noun] — tree [occ:2]
- `W00008`: **濡れる** (ぬれる) [verb] — to get wet [occ:1]
- `W00009`: **お茶** (おちゃ) [noun] — tea, green tea [occ:3]
- `W00010`: **飲みます** (のみます) [verb] — to drink [occ:1]
- `W00011`: **静か** (しずか) [adjective] — quiet, calm [occ:3]
- `W00012`: **温かい** (あたたかい) [adjective] — warm [occ:3]
- `W00013`: **いい** (いい) [adjective] — good, nice [occ:3]
- `W00014`: **気分** (きぶん) [noun] — feeling, mood [occ:3]
- `W00015`: **朝** (あさ) [noun] — morning [occ:2]
- `W00016`: **公園** (こうえん) [noun] — park [occ:1]
- `W00017`: **歩きます** (あるきます) [verb] — to walk [occ:1]
- `W00018`: **夕方** (ゆうがた) [noun] — evening, late afternoon [occ:1]
- `W00019`: **朝ごはん** (あさごはん) [noun] — breakfast [occ:1]
- `W00020`: **食べます** (たべます) [verb] — to eat [occ:1]
- `W00021`: **卵** (たまご) [noun] — egg [occ:1]
- `W00022`: **友達** (ともだち) [noun] — friend **[NEW]**
- `W00023`: **散歩** (さんぽ) [noun] — walk, stroll **[NEW]**
- `W00024`: **木** (き) [noun] — tree **[NEW]**

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
- `G011_ya_partial`: **[NEW grammar point — define in story]**

---

## New word definitions (introduce these in the story)

- `W00022`: **友達** (ともだち) [noun] — friend
- `W00023`: **散歩** (さんぽ) [noun] — walk, stroll
- `W00024`: **木** (き) [noun] — tree

---

## Output schema

Produce a `story_4.json` object with this structure:

```json
{
  "story_id": 4,
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
  "new_words": ["W00022", "W00023", "W00024"],
  "new_grammar": ["G011_ya_partial"],
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
