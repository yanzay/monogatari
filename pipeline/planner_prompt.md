# Monogatari — Story Planner Task

You are producing `plan.json` for story 9 of the Monogatari graded-reader.
Read everything below carefully. Output **only** the JSON object — no prose.

---

## Learner's current vocabulary (35 words)

- `W00001`: **今朝** (けさ) — this morning [occ:2, story:1]
- `W00002`: **雨** (あめ) — rain [occ:6, story:1]
- `W00003`: **私** (わたし) — I, me [occ:10, story:1]
- `W00004`: **窓** (まど) — window [occ:4, story:1]
- `W00005`: **外** (そと) — outside [occ:6, story:1]
- `W00006`: **見ます** (みます) — to see, to look [occ:8, story:1]
- `W00007`: **木** (き) — tree [occ:5, story:1]
- `W00008`: **濡れる** (ぬれる) — to get wet [occ:1, story:1]
- `W00009`: **お茶** (おちゃ) — tea, green tea [occ:6, story:1]
- `W00010`: **飲みます** (のみます) — to drink [occ:3, story:1]
- `W00011`: **静か** (しずか) — quiet, calm [occ:9, story:1]
- `W00012`: **温かい** (あたたかい) — warm [occ:5, story:1]
- `W00013`: **いい** (いい) — good, nice [occ:9, story:1]
- `W00014`: **気分** (きぶん) — feeling, mood [occ:6, story:1]
- `W00015`: **朝** (あさ) — morning [occ:5, story:1]
- `W00016`: **公園** (こうえん) — park [occ:4, story:2]
- `W00017`: **歩きます** (あるきます) — to walk [occ:4, story:2]
- `W00018`: **夕方** (ゆうがた) — evening, late afternoon [occ:3, story:2]
- `W00019`: **朝ごはん** (あさごはん) — breakfast [occ:1, story:3]
- `W00020`: **食べます** (たべます) — to eat [occ:1, story:3]
- `W00021`: **卵** (たまご) — egg [occ:1, story:3]
- `W00022`: **友達** (ともだち) — friend [occ:3, story:4]
- `W00023`: **散歩** (さんぽ) — walk, stroll [occ:2, story:4]
- `W00024`: **花** (はな) — flower [occ:3, story:4]
- `W00025`: **ドア** (ドア) — door [occ:1, story:5]
- `W00026`: **帰ります** (かえります) — to return home, to go back [occ:1, story:5]
- `W00027`: **風** (かぜ) — wind [occ:1, story:5]
- `W00028`: **猫** (ねこ) — cat [occ:1, story:6]
- `W00029`: **います** (います) — to be (animate); to exist (animate) [occ:1, story:6]
- `W00030`: **夜** (よる) — night [occ:1, story:7]
- `W00031`: **月** (つき) — moon [occ:1, story:7]
- `W00032`: **星** (ほし) — star [occ:1, story:7]
- `W00033`: **本** (ほん) — book [occ:1, story:8]
- `W00034`: **読む** (よむ) — to read [occ:1, story:8]
- `W00035`: **二人** (ふたり) — two people [occ:1, story:8]

## Learner's current grammar (12 points)

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

## Words most in need of reinforcement (occurrences < 5)

- `W00008`: **濡れる** (ぬれる) — to get wet [occ:1]
- `W00020`: **食べます** (たべます) — to eat [occ:1]
- `W00019`: **朝ごはん** (あさごはん) — breakfast [occ:1]
- `W00021`: **卵** (たまご) — egg [occ:1]
- `W00027`: **風** (かぜ) — wind [occ:1]
- `W00026`: **帰ります** (かえります) — to return home [occ:1]
- `W00025`: **ドア** (ドア) — door [occ:1]
- `W00029`: **います** (います) — to be (animate); to exist (animate) [occ:1]

---

## Difficulty policy for story 9

- Introduce exactly **3** new words.
- Optionally introduce at most **1** new grammar point(s). Zero is fine.
- Story length (from the library-wide progression curve in pipeline/progression.py):
  - **Target: 7 sentences, 18 content tokens.**
  - Acceptance band: 6–8 sentences, 13–25 content tokens.
  - The validator's Check 7 enforces these bands per story_id; the writer
    will be told the same target. Going outside the band fails the build.
- The validator's Check 6 enforces a *reinforcement floor* of low-occ
  tokens per story (replaces the old 60% percentage as of 2026-04-22).
  Hit the floor and you're done — the rest of the prose is free.
- New grammar prerequisites must all already exist in grammar_state.
- New words must be i+1: high-frequency, concrete, combinable with existing vocab.
- **No topic restrictions.** As of 2026-04-22 the validator no longer
  blocks any subject matter — choose whatever theme serves the story.
  *Hint:* themes the old policy forbade (loss, grief, conflict,
  romance, death, war, addiction, brand names, real people) are some
  of the strongest engagement levers available — actively consider
  them when planning. Cozy is fine but no longer the default. See
  `pipeline/authoring_rules.md` § 3 for the full hint.


## Next available word ID

The next sequential word ID is: **W00036**
(assign new IDs from here upward: W00036, W00037, W00038, …)

---

## Output schema

Produce this exact JSON object:

```json
{
  "story_id": 9,
  "target_word_count": 18,
  "max_sentences": 8,
  "new_words": ["<id1>", "<id2>", "<id3>"],
  "new_grammar": ["<gid>" ],
  "theme": "<2-5 word theme>",
  "setting": "<one sentence describing the scene>",
  "constraints": {
    "must_reuse_words": ["<up to 5 word_ids most needing reinforcement>"]
  },
  "new_word_definitions": {
    "<word_id>": {
      "surface": "<kanji form or kana if no kanji>",
      "kana": "<hiragana>",
      "reading": "<romaji>",
      "pos": "<noun|verb|adjective|adverb|pronoun>",
      "verb_class": "<ichidan|godan|null>",
      "adj_class": "<i|na|null>",
      "meanings": ["<primary English meaning>"],
      "grammar_tags": []
    }
  },
  "new_grammar_definitions": {
    "<grammar_id>": {
      "title": "<short Japanese form + English label, e.g. 'も — also / too'>",
      "short": "<one-line description shown in tooltips>",
      "long":  "<full explanation: usage, examples, common pitfalls>",
      "genki_ref": "<e.g. L2 or null>",
      "prerequisites": ["<existing grammar_id>", ...]
    }
  },
  "rationale": "<one paragraph explaining word choices>",
  "seed": <random integer>
}
```

> Every entry in `new_grammar` MUST have a corresponding entry in
> `new_grammar_definitions`. Ship-time state validation will reject placeholders.
