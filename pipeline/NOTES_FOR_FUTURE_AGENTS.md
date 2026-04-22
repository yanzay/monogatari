# Notes for future agents — read before authoring or reviewing

> Created 2026-04-22 after a library-wide audit found that several stories
> shipped with sentences the prior reviewer had labelled "small concerns"
> when they were in fact nonsense, mistranslations, or data-integrity
> bugs. This file is the in-context reminder of what went wrong, why,
> and how to avoid repeating it.

If you only have time for three things, read these:

1. The validator only checks legality, not sense. **Re-read every JP
   sentence as a human reader and ask "does this proposition hold in
   the world the story has built?"** before assigning any score.
2. **Glosses must reflect what the JP actually says** — every English
   verb must have a JP token behind it. No invented "open", "prepare",
   "leave ready" for verbs that are not present.
3. **`word_id` is a hard contract**: it must identify the lemma the
   surface form derives from. Never reuse a noun's word_id to smuggle
   in a verb. If you need a word that isn't in vocab, refuse the
   story (Section 7 of authoring_rules.md) and add the word the right
   way through `planner.py` / `lookup.py`.

## What the audit found (2026-04-22)

These were live in shipped stories before this audit:

| Story | Defect | Why it slipped through |
|-------|--------|------------------------|
| 7     | `月も雨を見ます` ("the moon looks at the rain") in a stars-and-moon story with no rain | reviewer scored "originality 4" without checking continuity |
| 8     | `私の本は静かです` glossed "the book in my hands is quiet" | books aren't silent; "in my hands" is calque English not in JP |
| 12    | `静かな月、夜だと思います` ("I think it is night") at night | と思います misused for a fact already known to the speaker |
| 14    | `飲んでおきます` glossed "leave the tea ready" + `明日の朝ごはんも食べます` ("I will eat tomorrow's breakfast today") | gloss inflation; future-of-future-tense nonsense |
| 15    | `行きます` tagged `word_id: W00047` (which is 空 / sora — a noun); broken JP `私は散歩、帰ります`; gloss "open the door" for `ドアを見て` ("look at the door") | reviewer never spot-checked that token word_ids match their lemma |

Cross-library issues:

- `静か` in 14 of 15 stories
- "look out the window" in 7 of 15
- `〜、いい朝/夜/気分です` closer template in 8 of 15
- `お茶` and `雨` each in 7 of 15

The reviewer's notes contained sentences like *"slight repetition vs.
last story"* under originality scores of 4. **An originality 4 with
that kind of qualitative finding is dishonest.** If the criticism is
real, the score must reflect it.

## Pipeline reading order for new authors

1. `pipeline/authoring_rules.md` — sections 6 (Engagement & voice) and
   especially the new **Semantic-sanity anti-patterns** and **Variety
   guard** subsections.
2. `pipeline/engagement_review_prompt.md` — the new **Honesty
   pre-check** at the bottom is mandatory before scoring.
3. `pipeline/engagement_baseline.md` — the **2026-04-22 (16:11
   audit)** entry in the History section explains every defect this
   audit caught.

## Concrete checklists you should run on every new story

### Author checklist (before sending to validate.py)

- [ ] For each content token: surface inflects from the lemma the
      `word_id` points to.
- [ ] For each `gloss_en`: every English content word has a JP token
      behind it. Cover the JP, read only the gloss, then uncover —
      they should match.
- [ ] For each sentence: the proposition holds in the world s0–s2
      established. (No moon at breakfast. No rain in a clear-sky
      story. No "the book is quiet".)
- [ ] For `〜と思います`: the speaker actually doesn't already know
      the embedded fact (it's an inference, opinion, or guess).
- [ ] For 〜ておく: the gloss conveys "go ahead and do X (in
      preparation)", not "leave X ready" / "prepare X".
- [ ] For future-tensed `明日のN`: N is something that *exists in
      the future and not yet*; you cannot eat tomorrow's breakfast
      today.

### Variety checklist (before approving)

- [ ] Open the previous 3 stories. List the dominant motifs (window,
      rain, cat, letter, moon, …). Pick a different one to lead with.
- [ ] If `静か` would close this story and `静か` closed the previous
      story — change one of them.
- [ ] If `〜、いい朝/夜/気分です` is your closer and the previous
      story used the same template — change yours.

### Reviewer honesty checklist (before scoring)

- [ ] Run the Honesty pre-check (engagement_review_prompt.md, last
      section). If any sense check fails, **rewrite the story line
      and re-validate** before scoring; do not approve with a "future
      author note".
- [ ] If your free-text notes contain "repetitive" or "similar to
      story N" or "calque", originality cannot be 4 or 5. Score 2 or
      3 and rewrite.

## Audio is stale after JP token edits

Audio files (`audio/story_N/sM.mp3` and `audio/story_N/w_WID.mp3`) are
generated from the JP token surfaces. If you edit any sentence's
tokens — even just to swap a particle — the corresponding `sM.mp3`
must be regenerated. The audit-rewrite of stories 7, 8, 12, 14, 15
**invalidated their existing audio**; regenerate via
`pipeline/audio_builder.py` (or whichever wrapper the build pipeline
uses) before shipping.

## Word vocabulary integrity

`data/vocab_state.json` currently has these particularly easy traps:

- W00047 = 空 (sora / sky), **noun**. Has been mistakenly used as the
  word_id for the verb 行く. There is no entry for 行く. If you need
  a verb of motion, restructure with what exists (歩く, 帰る, 来る).
- Several verbs are stored only in their `〜ます` form
  (e.g. `mimasu`, `nomimasu`). When inflecting to te-form / ta-form,
  derive from the dictionary form (`見る`, `飲む`) and put the
  `inflection.base` field accordingly. The validator's
  `expected_inflection` helper catches mismatches as warnings — do
  not ignore them silently.

## Theme palette suggestions (the library is over-leaning)

Underused palette entries (use these to break the rain/window/cat
loop):

- 卵 / 朝ごはん — kitchen scene, breakfast prep
- 椅子 / 机 / 本 — desk-side, single-object focus
- 公園 + 花 / 木 — outdoor walking scenes (used early but neglected
  since story 5)
- 二人 / 友達 — explicit dual-protagonist scenes
- 寝ます — bedtime / cat-sleeping closers
- 星 / 空 — celestial scenes (used twice; room for variation in
  weather, time-of-day, mood)

The pattern that works best, per the leaderboard, is *adding a new
character, prop, or setting* — see story 6 (cat as new presence),
story 8 (parallel two-person reading), story 10 (offstage friend via
letter). The pattern that scores worst is *recycling the previous
story's setting with one variable swapped*.
