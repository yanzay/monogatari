# Monogatari — Story Writer Task

You are writing story **27** for the Monogatari Japanese graded-reader.
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

- **New words need ≥ 1 occurrence in the introducing story.** A second
  occurrence is welcome but no longer required (relaxed 2026-04-22). The
  reason: the old "≥ 2x in this story" rule was the engine of the
  worksheet-y `私は本を読みます。/友達も本を読みます。` parallel-pair
  construction. Reinforcement is now a *library*-level concern: the
  validator's Check 6 starvation alarm flags any low-occ word that has
  not been seen in the last 5 stories, and the next planner's
  `--weak` list will surface candidates for the next story to revisit.
  If a second occurrence in the same story falls naturally out of the
  prose, keep it; if it would force a parallel-pair, don't.

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

- **Setting suggestions** (not requirements; pick whatever serves the
  story you want to write):
  home, kitchen, garden, park, café, train, school, weather, morning/evening
  routines, small emotions (tired, calm, curious, a little lonely, content).

- **No topic restrictions.** As of 2026-04-22 the validator no longer
  blocks any subject matter (the old "Avoid absolutely" list was
  removed along with Check 8). Any theme is allowed — violence,
  romance, politics, religion, death, drugs, brand names, real people,
  any of the things the older draft of this document forbade. Choose
  whatever subject matter the *story* needs. The other content rules
  (concrete imagery, narrative arc, semantic sanity, faithful gloss)
  still apply regardless of theme.

- **Embrace high-stakes themes — they are usually engagement gold.**
  The cozy-only library that grew under the old rules became
  forgettable precisely because every story pulled back from anything
  with stakes. The themes the old policy forbade are some of the
  *best* engagement levers you have:
  - **Loss & grief** — a missing cat, a friend who stopped writing,
    an empty chair at the table. A six-sentence story about a small
    grief lands harder than a six-sentence story about tea.
  - **Conflict & quiet anger** — an argument with a friend, a
    sibling who took your book, a neighbour playing music too loud.
    Even at beginner vocab you can do "the friend doesn't speak. I
    drink my tea. The tea is cold."
  - **Romance & intimacy** — a first date, a remembered hand, a
    letter that could be read two ways. Quiet eroticism doesn't need
    explicit vocab; it needs implication.
  - **Death, illness, mortality** — the cat is old. The grandmother
    sleeps a lot now. A snowfall on the day of a funeral. These are
    the universal subjects — graded readers that lean into them
    feel like literature, not flashcards.
  - **Politics, war, displacement** — refugee in a new country,
    family separated by a border, a soldier writing home. The N5
    vocab can absolutely carry a war story; what makes it a war
    story is the *omissions*, not heavy vocabulary.
  - **Drugs, alcohol, addiction** — a cup of sake at the end of a
    long day, a friend who drinks too much, a morning of regret.
  - **Brand names, real people, real places** — `スターバックス`,
    `村上春樹`, `京都駅`. Specificity beats vagueness; "the café"
    is forgettable, "Doutor at 7am on a Tuesday" is alive.

  None of this requires graphic detail. Restraint at the *imagery*
  level is what makes hard topics work in beginner prose: imply, do
  not show. The most powerful sentence in a grief story is often
  the one that doesn't mention the loss directly. *That* is the
  craft you should be reaching for now that the topic gate is gone.

- **Cozy is still allowed, just no longer the default.** A small
  observational morning is a perfectly valid story. The point of
  removing the gate is not "every story must be heavy" — it is "the
  agent should pick the theme the story needs, and high-stakes
  themes are now an option on equal footing with cozy ones".

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

  **Never pad or stretch the gloss to satisfy Check 9's length ratio.**
  Check 9 measures `EN_words / (content + aux JP tokens)` — particles
  are excluded from the denominator (since they don't surface in
  English) so a natural short gloss like "I am happy." for 私は嬉しい
  です passes. If a faithful gloss still trips the warning band, the
  fix is to revisit the JP (is it actually saying what you mean?), not
  to inflate the English with filler ("As for me, I am happy" is a
  validator hack, not an honest translation). See docs/authoring.md
  G4 / v0.15 for the bands and rationale.

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
- **Gloss inflation / mistranslation.** Don't write `gloss_en` "After
  that, I eat my breakfast." if the JP has no それから. Glosses must
  faithfully reflect *what is in the JP*. If the JP token sequence
  doesn't say "open", the gloss may not say "open". If the JP says
  「飲んでおきます」, the gloss must convey the ~ておく nuance ("go
  ahead and drink in advance"), not invent "leave the tea ready".
- **Subject-grind.** Five `私は…` openers in a row. Drop the subject
  when context allows — Japanese is generous about this and the
  narrator immediately sounds less like a worksheet.

### Semantic-sanity anti-patterns (the "is this even a sentence?" bar)

A sentence may pass closed-vocab + grammar validation and still be
**nonsense**. These are the recurring failure modes seen in stories
1–15. If you catch yourself writing one, stop and rewrite the line.

- **Inanimate things ascribed observer/agent properties.**
  `私の本は静かです` ("the book is quiet"). Books, letters, eggs do
  not have a faculty of being silent. Quietness belongs to *people,
  rooms, places, weather, animals* — never to objects. Same goes for
  `お茶は温かいです` (fine — temperature) vs `お茶は静かです` (not fine).
- **Imagery the story did not establish.** `月も雨を見ます` ("the moon
  also looks at the rain") in a *night-and-stars* story that never
  mentioned rain. Every image must be motivated by something earlier
  in the same story. If you reach for a motif, check it appears in an
  earlier sentence; if not, either add it earlier or pick a different
  closer.
- **`〜と思います` for facts the narrator already knows.**
  `静かな月、夜だと思います` ("Quiet moon — I think it is night")
  while the narrator is *already at night*. と思います is for
  inferences, hypotheses, opinions. It is not a hedge to bolt onto a
  fact. Use it for `猫はいい友達だと思います` (opinion) or
  `猫も窓を見ると思います` (inference about another's behaviour).
- **Future-tense actions whose completion happens before the present
  time.** `明日のお茶を飲みます` ("I will drink tomorrow's tea") spoken
  *today* is illogical — tomorrow's tea does not yet exist. Either
  drop the 「明日の」 or change the verb to 〜ておく ("I'll go ahead
  and drink some now") and let the gloss reflect the prep nuance.
- **Calque English literalism.** `本は静かです` glossed as "the book in
  my hands is quiet" inserts "in my hands" out of nowhere; the JP has
  no such phrase. The gloss is for comprehension of the JP, not for
  rescuing a sentence the JP does not actually convey.
- **Word_id ≠ surface.** Tagging `行きます` with `word_id: W00047`
  because there's no entry for 行く is a data crime. If a verb you
  need is not in vocab, restructure the sentence. The word_id must
  always identify the actual lemma the surface inflects from.
- **Setting/time mismatch.** `今朝、月を見ます` ("This morning, I look
  at the moon") — the moon is generally not visible in the morning.
  Same for "stars at noon", "sun at midnight", "rain in the desert
  apartment". Check that the time-of-day in s0/s1 is consistent with
  every observation later in the story.

### Variety guard (how to stop the library sounding the same)

The library currently leans hard on a small palette: 窓 / 雨 / 静か /
お茶 / look-out-the-window / "いい朝です" closer. Before authoring,
glance at the recent 3–5 stories and *don't repeat* the most prominent
motifs unless you are explicitly building on them.

- **Window-and-look quota.** No more than one "look out the window"
  scene every 4 stories. If your draft has the narrator at the window
  and the previous story did too, change setting (porch, kitchen,
  desk-side, café table, garden bench).
- **Adjective rotation.** `静か` is a useful word but the library
  reaches for it as a default. If the previous story already closed
  on `静か`, pick `温かい`, `いい`, or describe the scene in nouns
  (`月と星、夜の空。`) instead of adjectives.
- **Closer rotation.** `〜、いい朝/夜/気分です` is a strong template
  but it has been used in stories 1, 4, 6, 7, 8, 9, 11, 13. Find
  another shape: a short sentence-fragment image
  (`窓のそばの本。`), a question to nobody (`明日も雨かな。`), a
  sensory verb beat (`星を見ます。`). Don't always cash out the story
  on a feeling.
- **Theme rotation.** Look at the last three stories' themes (weather,
  cat, friend-letter, books, etc.) and pick something else. The
  recent over-rotation on rain + cat + letter is exactly the failure
  mode this guard exists to prevent.

---

## 6.5 Validator philosophy: content first, math second

The validator (`pipeline/validate.py`) was reformed on 2026-04-22 to stop
fighting natural prose. The old regime had three rules that were quietly
*causing* the nonsense and repetition the audit caught:

1. **Old Check 6** demanded ≥ 60 % of content tokens be "low-occ" — which
   forced authors to pad with weird-noun-heavy sentences once natural
   verbs/adjectives crossed the lifetime threshold. **Replaced** with
   an absolute floor (≥ 6 low-occ tokens, or ≤ 30 % of target — whichever
   is smaller). Once you've hit the floor, the rest of the prose is free.
2. **Old Check 4** required every new noun to appear ≥ 2× in the same
   story — the engine of the parallel-pair worksheet feel. **Relaxed**
   to ≥ 1× for vocabulary; new *grammar* still requires ≥ 2× because a
   pattern needs to be visible twice to register as a pattern.
3. **Old Check 8** was bag-of-words on the English gloss, so "I love
   rain" tripped it. **Replaced** with a small phrase blacklist that
   targets actual unsafe content.

Two new content-quality checks were added:

- **Check 11 — Semantic-sanity lint** (errors and warnings). A
  conservative pattern table that catches the actual nonsense the audit
  found: inanimate-thing-is-quiet (`本は静かです`), tomorrow's-X-eaten-
  today (`明日のお茶を飲みます`), `〜と思います` for self-known
  facts (`夜だと思います` at night), word_id-points-at-wrong-pos, and
  lonely scene nouns. Rules are deliberately narrow — they only fire on
  patterns we have direct audit evidence cause defects, and they
  exclude common JP idioms (静かな月, 静かな朝, 静かな部屋 are all fine).
- **Check 12 — Motif rotation** (warning only). Surfaces high
  vocabulary overlap (Jaccard ≥ 55 %) with any of the previous 3
  stories. Never blocks ship; the engagement reviewer decides whether
  the continuation is justified.

A **review-honesty gate** (`pipeline/review_lint.py`) was added to
the engagement review. If the reviewer's free-text notes contain
"repetitive", "calque", "awkward", "nonsense", etc. and the
corresponding numeric score is > 3, the review is rejected. This
forces the score to reflect the prose-level criticism the reviewer
already wrote down.

### What this means for the author

- **Don't twist the prose to satisfy a percentage.** There is no
  percentage anymore. Hit the absolute floor of 6 low-occ tokens and
  the math is done. Pick the next sentence for what the *story* needs.
- **Don't repeat a noun "for reinforcement".** A second occurrence
  that falls naturally out of the scene is welcome; one wedged in to
  satisfy a counter is what made stories 1–10 sound like worksheets.
- **Trust the starvation alarm.** When validate.py warns "W00018 has
  not appeared in the last 5 stories", that is the system telling
  the *next* planner to use 卵 — not telling *you* to wedge it into
  this story.
- **Treat Check 11 errors as content bugs.** They are not arbitrary;
  every rule comes from a real shipped defect. If a Check 11 error
  fires on your draft, the JP literally doesn't make sense — fix the
  prose, don't disable the rule.
- **Treat Check 12 warnings as a planning prompt.** A 60 % overlap
  with the previous story is a sign you're recycling the setting;
  rotate the theme.

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
  "story_id": 27,
  "target_word_count": 29,
  "max_sentences": 12,
  "new_words": [
    "W00081",
    "W00082",
    "W00083"
  ],
  "new_grammar": [],
  "theme": "Summer in the garden",
  "setting": "A hot summer day in the narrator's garden. Beautiful flowers, a chair under a tree, the cat sleeping, a bird visiting. The narrator drinks tea, watches, thinks the garden is beautiful.",
  "constraints": {
    "must_reuse_words": [
      "W00043",
      "W00038",
      "W00036",
      "W00059",
      "W00054",
      "W00024"
    ]
  },
  "new_word_definitions": {
    "W00081": {
      "surface": "夏",
      "kana": "なつ",
      "reading": "natsu",
      "pos": "noun",
      "verb_class": null,
      "adj_class": null,
      "meanings": [
        "summer"
      ],
      "grammar_tags": []
    },
    "W00082": {
      "surface": "暑い",
      "kana": "あつい",
      "reading": "atsui",
      "pos": "adjective",
      "verb_class": null,
      "adj_class": "i",
      "meanings": [
        "hot (weather)"
      ],
      "grammar_tags": []
    },
    "W00083": {
      "surface": "美しい",
      "kana": "うつくしい",
      "reading": "utsukushii",
      "pos": "adjective",
      "verb_class": null,
      "adj_class": "i",
      "meanings": [
        "beautiful"
      ],
      "grammar_tags": []
    }
  },
  "new_grammar_definitions": {},
  "rationale": "Story 27 brings 思います back into rotation (last seen story 20), reinforces the story-18 garden-furniture cluster (椅子, 寝ます), and introduces the second seasonal anchor 夏 to pair with 春 from story 24. The garden is the same location as story 19 but the season has changed — the same physical space rendered in two different conditions is a stronger story-pair pattern than 'cat at window' for the third time. 美しい unlocks aesthetic register the library has lacked; 暑い completes the temperature-i-adjective triad with 寒い (story 20) and 温かい (already in vocab).",
  "seed": 142568
}
```

---

## Allowed vocabulary (ALL words you may use — no others)

- `W00001`: **今朝** (けさ) [noun] — this morning [occ:10]
- `W00002`: **雨** (あめ) [noun] — rain [occ:8]
- `W00003`: **私** (わたし) [pronoun] — I, me [occ:25]
- `W00004`: **窓** (まど) [noun] — window [occ:9]
- `W00005`: **外** (そと) [noun] — outside [occ:9]
- `W00006`: **見ます** (みます) [verb] — to see, to look [occ:16]
- `W00007`: **木** (き) [noun] — tree [occ:5]
- `W00008`: **濡れる** (ぬれる) [verb] — to get wet [occ:3]
- `W00009`: **お茶** (おちゃ) [noun] — tea, green tea [occ:10]
- `W00010`: **飲みます** (のみます) [verb] — to drink [occ:6]
- `W00011`: **静か** (しずか) [adjective] — quiet, calm [occ:19]
- `W00012`: **温かい** (あたたかい) [adjective] — warm [occ:11]
- `W00013`: **いい** (いい) [adjective] — good, nice [occ:9]
- `W00014`: **気分** (きぶん) [noun] — feeling, mood [occ:5]
- `W00015`: **朝** (あさ) [noun] — morning [occ:14]
- `W00016`: **公園** (こうえん) [noun] — park [occ:5]
- `W00017`: **歩きます** (あるきます) [verb] — to walk [occ:5]
- `W00018`: **夕方** (ゆうがた) [noun] — evening, late afternoon [occ:5]
- `W00019`: **朝ごはん** (あさごはん) [noun] — breakfast [occ:4]
- `W00020`: **食べます** (たべます) [verb] — to eat [occ:4]
- `W00021`: **卵** (たまご) [noun] — egg [occ:3]
- `W00022`: **友達** (ともだち) [noun] — friend [occ:15]
- `W00023`: **散歩** (さんぽ) [noun] — walk, stroll [occ:2]
- `W00024`: **花** (はな) [noun] — flower [occ:4]
- `W00025`: **ドア** (ドア) [noun] — door [occ:4]
- `W00026`: **帰ります** (かえります) [verb] — to return home, to go back [occ:5]
- `W00027`: **風** (かぜ) [noun] — wind [occ:5]
- `W00028`: **猫** (ねこ) [noun] — cat [occ:5]
- `W00029`: **います** (います) [verb] — to be (animate), to exist [occ:7]
- `W00030`: **夜** (よる) [noun] — night [occ:5]
- `W00031`: **月** (つき) [noun] — moon [occ:5]
- `W00032`: **星** (ほし) [noun] — star [occ:3]
- `W00033`: **本** (ほん) [noun] — book [occ:6]
- `W00034`: **読みます** (よみます) [verb] — to read [occ:8]
- `W00035`: **二人** (ふたり) [noun] — two people [occ:4]
- `W00036`: **椅子** (いす) [noun] — chair [occ:3]
- `W00037`: **机** (つくえ) [noun] — desk [occ:8]
- `W00038`: **寝ます** (ねます) [verb] — to sleep [occ:3]
- `W00039`: **手紙** (てがみ) [noun] — letter, note [occ:5]
- `W00040`: **来ます** (きます) [verb] — to come, to arrive [occ:8]
- `W00041`: **待ちます** (まちます) [verb] — to wait [occ:4]
- `W00042`: **昨日** (きのう) [noun] — yesterday [occ:5]
- `W00043`: **思います** (おもいます) [verb] — to think [occ:4]
- `W00044`: **あります** (あります) [verb] — to exist (inanimate), to be (inanimate) [occ:12]
- `W00045`: **そば** (そば) [noun] — side, near [occ:3]
- `W00046`: **明日** (あした) [noun] — tomorrow [occ:3]
- `W00047`: **空** (そら) [noun] — sky [occ:3]
- `W00048`: **作ります** (つくります) [verb] — to make, to prepare [occ:2]
- `W00049`: **パン** (パン) [noun] — bread [occ:3]
- `W00050`: **一緒に** (いっしょに) [adverb] — together [occ:3]
- `W00051`: **子供** (こども) [noun] — child [occ:2]
- `W00052`: **ベンチ** (ベンチ) [noun] — bench [occ:1]
- `W00053`: **笑います** (わらいます) [verb] — to smile, to laugh [occ:4]
- `W00054`: **鳥** (とり) [noun] — bird [occ:2]
- `W00055`: **小さい** (ちいさい) [adjective] — small, little [occ:4]
- `W00056`: **嬉しい** (うれしい) [adjective] — happy, glad [occ:3]
- `W00057`: **大きい** (おおきい) [adjective] — big, large [occ:3]
- `W00058`: **元気** (げんき) [adjective] — lively, energetic, healthy [occ:1]
- `W00059`: **庭** (にわ) [noun] — garden, yard [occ:2]
- `W00060`: **書きます** (かきます) [verb] — to write [occ:1]
- `W00061`: **名前** (なまえ) [noun] — name [occ:1]
- `W00062`: **寒い** (さむい) [adjective] — cold (weather) [occ:1]
- `W00063`: **雪** (ゆき) [noun] — snow [occ:2]
- `W00064`: **道** (みち) [noun] — road, path [occ:3]
- `W00065`: **一人** (ひとり) [noun] — one person, alone [occ:2]
- `W00066`: **新しい** (あたらしい) [adjective] — new [occ:1]
- `W00067`: **古い** (ふるい) [adjective] — old (of objects) [occ:2]
- `W00068`: **写真** (しゃしん) [noun] — photograph, photo [occ:2]
- `W00069`: **駅** (えき) [noun] — train station [occ:1]
- `W00070`: **電車** (でんしゃ) [noun] — train [occ:1]
- `W00071`: **時計** (とけい) [noun] — clock, watch [occ:1]
- `W00072`: **春** (はる) [noun] — spring (season) [occ:1]
- `W00073`: **開けます** (あけます) [verb] — to open [occ:2]
- `W00074`: **長い** (ながい) [adjective] — long [occ:1]
- `W00075`: **部屋** (へや) [noun] — room [occ:2]
- `W00076`: **悲しい** (かなしい) [adjective] — sad [occ:1]
- `W00077`: **出ます** (でます) [verb] — to go out, to leave [occ:1]
- `W00078`: **家** (いえ) [noun] — house, home [occ:1]
- `W00079`: **鍵** (かぎ) [noun] — key [occ:1]
- `W00080`: **入ります** (はいります) [verb] — to enter, to go in [occ:1]
- `W00081`: **夏** (なつ) [noun] — summer **[NEW]**
- `W00082`: **暑い** (あつい) [adjective] — hot (weather) **[NEW]**
- `W00083`: **美しい** (うつくしい) [adjective] — beautiful **[NEW]**

---

## Allowed grammar (ALL grammar_ids you may use — no others)

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

---

## New word definitions (introduce these in the story)

- `W00081`: **夏** (なつ) [noun] — summer
- `W00082`: **暑い** (あつい) [adjective · i-adj] — hot (weather)
- `W00083`: **美しい** (うつくしい) [adjective · i-adj] — beautiful

---

## Output schema

Produce a `story_27.json` object with this structure:

```json
{
  "story_id": 27,
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
  "new_words": ["W00081", "W00082", "W00083"],
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
