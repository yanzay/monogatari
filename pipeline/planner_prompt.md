# Monogatari — Story Planner Task

You are producing `plan.json` for story 18 of the Monogatari graded-reader.
Read everything below carefully. Output **only** the JSON object — no prose.

---

## Learner's current vocabulary (53 words)

- `W00001`: **今朝** (けさ) — this morning [occ:4, story:story_1]
- `W00002`: **雨** (あめ) — rain [occ:6, story:story_1]
- `W00003`: **私** (わたし) — I, me [occ:16, story:story_1]
- `W00004`: **窓** (まど) — window [occ:7, story:story_1]
- `W00005`: **外** (そと) — outside [occ:5, story:story_1]
- `W00006`: **見ます** (みます) — to see, to look [occ:13, story:story_1]
- `W00007`: **木** (き) — tree [occ:5, story:story_1]
- `W00008`: **濡れる** (ぬれる) — to get wet [occ:2, story:story_1]
- `W00009`: **お茶** (おちゃ) — tea, green tea [occ:8, story:story_1]
- `W00010`: **飲みます** (のみます) — to drink [occ:5, story:story_1]
- `W00011`: **静か** (しずか) — quiet, calm [occ:14, story:story_1]
- `W00012`: **温かい** (あたたかい) — warm [occ:5, story:story_1]
- `W00013`: **いい** (いい) — good, nice [occ:9, story:story_1]
- `W00014`: **気分** (きぶん) — feeling, mood [occ:5, story:story_1]
- `W00015`: **朝** (あさ) — morning [occ:9, story:story_1]
- `W00016`: **公園** (こうえん) — park [occ:5, story:story_2]
- `W00017`: **歩きます** (あるきます) — to walk [occ:5, story:story_2]
- `W00018`: **夕方** (ゆうがた) — evening, late afternoon [occ:3, story:story_2]
- `W00019`: **朝ごはん** (あさごはん) — breakfast [occ:3, story:story_3]
- `W00020`: **食べます** (たべます) — to eat [occ:3, story:story_3]
- `W00021`: **卵** (たまご) — egg [occ:2, story:story_3]
- `W00022`: **友達** (ともだち) — friend [occ:10, story:story_2]
- `W00023`: **散歩** (さんぽ) — walk, stroll [occ:1, story:story_4]
- `W00024`: **花** (はな) — flower [occ:2, story:story_4]
- `W00025`: **ドア** (ドア) — door [occ:2, story:story_5]
- `W00026`: **帰ります** (かえります) — to return home, to go back [occ:2, story:story_5]
- `W00027`: **風** (かぜ) — wind [occ:5, story:story_5]
- `W00028`: **猫** (ねこ) — cat [occ:4, story:story_6]
- `W00029`: **います** (います) — to be (animate), to exist [occ:6, story:story_6]
- `W00030`: **夜** (よる) — night [occ:4, story:story_7]
- `W00031`: **月** (つき) — moon [occ:4, story:story_7]
- `W00032`: **星** (ほし) — star [occ:2, story:story_7]
- `W00033`: **本** (ほん) — book [occ:5, story:story_8]
- `W00034`: **読みます** (よみます) — to read [occ:6, story:story_8]
- `W00035`: **二人** (ふたり) — two people [occ:2, story:story_8]
- `W00036`: **椅子** (いす) — chair [occ:2, story:story_9]
- `W00037`: **机** (つくえ) — desk [occ:3, story:story_9]
- `W00038`: **寝ます** (ねます) — to sleep [occ:2, story:story_9]
- `W00039`: **手紙** (てがみ) — letter, note [occ:3, story:story_10]
- `W00040`: **来ます** (きます) — to come, to arrive [occ:5, story:story_10]
- `W00041`: **待ちます** (まちます) — to wait [occ:3, story:story_10]
- `W00042`: **昨日** (きのう) — yesterday [occ:3, story:story_11]
- `W00043`: **思います** (おもいます) — to think [occ:2, story:story_12]
- `W00044`: **あります** (あります) — to exist (inanimate), to be (inanimate) [occ:5, story:story_7]
- `W00045`: **そば** (そば) — side, near [occ:2, story:story_13]
- `W00046`: **明日** (あした) — tomorrow [occ:2, story:story_14]
- `W00047`: **空** (そら) — sky [occ:1, story:story_15]
- `W00048`: **作ります** (つくります) — to make, to prepare [occ:1, story:story_16]
- `W00049`: **パン** (パン) — bread [occ:1, story:story_16]
- `W00050`: **一緒に** (いっしょに) — together [occ:2, story:story_16]
- `W00051`: **子供** (こども) — child [occ:1, story:story_17]
- `W00052`: **ベンチ** (ベンチ) — bench [occ:1, story:story_17]
- `W00053`: **笑います** (わらいます) — to smile, to laugh [occ:1, story:story_17]

## Learner's current grammar (20 points)

- `G001_wa_topic`: は — topic marker — Marks the topic of the sentence. Pronounced 'wa', not 'ha'.
- `G002_ga_subject`: が — subject marker — Subject marker. Contrasts with は: が emphasizes the subject; は sets the topic.
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
- `G013_mashita_past`: 〜ました — polite past tense — Past tense of polite verbs and です: 〜ます becomes 〜ました, です becomes でした.
- `G014_to_omoimasu`: 〜と思います — I think that ~ / I think it is ~
- `G015_no_possessive`: の — possessive / attributive — Links nouns: A の B = 'B of A' or 'A's B'.
- `G016_na_adjective`: な-adjectives — noun-like adjectives — Adjectives that take な before a noun (静かな猫). Behave like nouns with the copula.
- `G017_de_means`: で — by means / at (location of action) — Marks the means/instrument or the location where an action takes place.
- `G018_toki_when`: 〜とき — when — temporal subordinate clause
- `G019_te_oku`: 〜ておく — do in advance — Marks an action done beforehand in preparation for a later time or situation.
- `G020_te_kara`: 〜てから — after doing — Connects two actions in sequence: do A, then do B.

## Words most in need of reinforcement (occurrences < 5)

- `W00023`: **散歩** (さんぽ) — walk [occ:1]
- `W00047`: **空** (そら) — sky [occ:1]
- `W00049`: **パン** (パン) — bread [occ:1]
- `W00048`: **作ります** (つくります) — to make, to prepare [occ:1]
- `W00051`: **子供** (こども) — child [occ:1]
- `W00052`: **ベンチ** (ベンチ) — bench [occ:1]
- `W00053`: **笑います** (わらいます) — to smile, to laugh [occ:1]
- `W00008`: **濡れる** (ぬれる) — to get wet [occ:2]

---

## Difficulty policy for story 18

- Introduce exactly **3** new words.
- Optionally introduce at most **1** new grammar point(s). Zero is fine.
- Story length (from the library-wide progression curve in pipeline/progression.py):
  - **Target: 9 sentences, 23 content tokens.**
  - Acceptance band: 8–10 sentences, 16–34 content tokens.
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

The next sequential word ID is: **W00054**
(assign new IDs from here upward: W00054, W00055, W00056, …)

---

## Output schema

Produce this exact JSON object:

```json
{
  "story_id": 18,
  "target_word_count": 23,
  "max_sentences": 10,
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
