# Monogatari — Story Planner Task

You are producing `plan.json` for story 3 of the Monogatari graded-reader.
Read everything below carefully. Output **only** the JSON object — no prose.

---

## Learner's current vocabulary (18 words)

- `W00001`: **今朝** (けさ) — this morning [occ:2, story:1]
- `W00002`: **雨** (あめ) — rain [occ:2, story:1]
- `W00003`: **私** (わたし) — I, me [occ:3, story:1]
- `W00004`: **窓** (まど) — window [occ:1, story:1]
- `W00005`: **外** (そと) — outside [occ:2, story:1]
- `W00006`: **見ます** (みます) — to see, to look [occ:2, story:1]
- `W00007`: **木** (き) — tree [occ:2, story:1]
- `W00008`: **濡れる** (ぬれる) — to get wet [occ:1, story:1]
- `W00009`: **お茶** (おちゃ) — tea, green tea [occ:2, story:1]
- `W00010`: **飲みます** (のみます) — to drink [occ:1, story:1]
- `W00011`: **静か** (しずか) — quiet, calm [occ:2, story:1]
- `W00012`: **温かい** (あたたかい) — warm [occ:2, story:1]
- `W00013`: **いい** (いい) — good, nice [occ:2, story:1]
- `W00014`: **気分** (きぶん) — feeling, mood [occ:2, story:1]
- `W00015`: **朝** (あさ) — morning [occ:1, story:1]
- `W00016`: **公園** (こうえん) — park [occ:1, story:2]
- `W00017`: **歩きます** (あるきます) — to walk [occ:1, story:2]
- `W00018`: **夕方** (ゆうがた) — evening, late afternoon [occ:1, story:2]

## Learner's current grammar (9 points)

- `G001_wa_topic`: は — topic marker — Marks the topic of the sentence. Pronounced 'wa', not 'ha'.
- `G002_ga_subject`: が — subject marker — Marks the grammatical subject of the sentence.
- `G003_desu`: です — polite copula — Polite form of 'to be'. Links a topic to a description.
- `G004_ni_location`: に — location / direction marker — Marks the location of existence or the direction of movement.
- `G005_wo_object`: を — direct object marker — Marks the direct object of a verb.
- `G006_kara_from`: から — from — Marks a starting point in space, time, or reason.
- `G007_te_form`: て-form — connective verb form — Connects clauses or acts as a base for compound forms like て-います.
- `G008_te_iru`: 〜ています — ongoing state / action in progress — Expresses an action in progress or a resulting state.
- `G009_mo_also`: も — also / too — Marks something as additional. Replaces は or が when 'X too / X also' is meant.

## Words most in need of reinforcement (occurrences < 5)

- `W00004`: **窓** (まど) — window [occ:1]
- `W00008`: **濡れる** (ぬれる) — to get wet [occ:1]
- `W00010`: **飲みます** (のみます) — to drink [occ:1]
- `W00015`: **朝** (あさ) — morning [occ:1]
- `W00017`: **歩きます** (あるきます) — to walk [occ:1]
- `W00018`: **夕方** (ゆうがた) — evening [occ:1]
- `W00016`: **公園** (こうえん) — park [occ:1]
- `W00001`: **今朝** (けさ) — this morning [occ:2]

---

## Difficulty policy for story 3

- Introduce exactly **3** new words.
- Optionally introduce at most **1** new grammar point(s). Zero is fine.
- Story length: 5–8 sentences, 35–65 content tokens total.
- At least 60% of content tokens must be previously-seen words with occurrences < 5.
- New grammar prerequisites must all already exist in grammar_state.
- New words must be i+1: high-frequency, concrete, combinable with existing vocab.
- Avoid: violence, romance beyond friendship, politics, religion, graphic content.
- Theme hint: "morning kitchen"

## Next available word ID

The next sequential word ID is: **W00019**
(assign new IDs from here upward: W00019, W00020, W00021, …)

---

## Output schema

Produce this exact JSON object:

```json
{
  "story_id": 3,
  "target_word_count": <integer 35-65>,
  "max_sentences": 8,
  "new_words": ["<id1>", "<id2>", "<id3>"],
  "new_grammar": ["<gid>" ],
  "theme": "<2-5 word theme>",
  "setting": "<one sentence describing the scene>",
  "constraints": {
    "must_reuse_words": ["<up to 5 word_ids most needing reinforcement>"],
    "forbidden_words": [],
    "avoid_topics": ["violence", "romance", "politics"]
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
