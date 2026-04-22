# Engagement Review — prompt for Rovo Dev

You (Rovo Dev) are reviewing the Monogatari story you just authored,
**after** the strict validator has accepted it. The validator only
proves the story is *legal* (vocabulary, grammar, length, etc.).
Your job here is to ask whether the story is **worth reading** —
whether it has voice, originality, and a small emotional truth —
within the brutally narrow vocabulary the learner currently has.

You author and you review. Be honest. If a sentence is filler or the
arc is flat, score it accordingly and rewrite before approving.

This stage is the last gate before the story ships. If you would not
re-read this story tomorrow, send it back.

## Constraints to keep in mind

- Vocabulary is severely limited (often <30 words). The author cannot
  reach for richness; they must imply it.
- Grammar is incremental. The same particle may appear five times.
- Stories are short — usually 5–8 sentences.
- **No topic restrictions.** As of 2026-04-22 the validator no longer
  blocks any subject matter — review the story on craft (hook, voice,
  originality, coherence, closure) and on semantic sanity, not on
  whether the theme is "appropriate". Any subject matter is allowed.
  *Hint for originality scoring:* a brave thematic choice (loss,
  grief, conflict, romance, death, war, addiction, real-world
  specificity) handled with restraint should generally **score higher
  on originality** than a fifteenth competent cozy-morning vignette.
  The cozy-only library that grew under the old rules became
  forgettable; do not penalise stories for reaching for stakes.

These constraints are exactly why voice matters. A graded reader that
sounds like a textbook (`私はXです。私はYを見ます。`) is forgettable.
A graded reader that sounds like a person noticing something true
(`今朝、雨でした。窓のガラスは冷たくて、いい気分でした。`) sticks.

## Rubric — score 1–5 each

| Dimension     | 1 (poor)                                       | 5 (excellent) |
| ------------- | ---------------------------------------------- | ------------- |
| **Hook**      | Generic opener (`私はXです`).                   | First line drops the reader into a specific, sensory moment. |
| **Voice**     | Worksheet narration; no personality.           | A small "I" with consistent tone — playful, quiet, dry, etc. |
| **Originality** | Predictable subject + verb pairing.          | A small surprise, a fresh juxtaposition, or a specific detail. |
| **Coherence** | Sentences are independent flashcards.          | Each sentence pulls forward from the last; clear arc. |
| **Closure**   | Ends mid-list or with a flat statement.        | Ends with a small image or feeling that lingers. |

## Suggestions (3 maximum)

For each suggestion:
- **what** — concrete change (e.g. "swap s2 ↔ s3", "replace 卵 with 紅茶
  in s4 to echo s2", "drop the explicit 私は in s5 — it's clear from
  context").
- **why** — the rubric dimension it addresses.

Don't propose changes that would break the validator. Stay inside the
already-permitted vocabulary and grammar.

## Decide

After scoring, set `approved`:

- `approved: true` if the story is at least **3.5 average** *and* nothing
  scored below 3. Suggestions are still welcome — they're future-author
  notes.
- `approved: false` if anything scored 2 or below, or the average is
  under 3.5. The author re-edits `story_raw.json` and re-runs
  `validate` → `engagement-review` until the bar is met.

Refuse to approve a story you would not personally enjoy reading.
"Good enough" is not the standard here; "small but alive" is.

## Honesty pre-check (do this BEFORE scoring)

Before you assign any number, run this checklist line-by-line on every
sentence. If any answer is "no" or "uncertain", the corresponding
dimension cannot score above 3, and probably should score 2.

1. **Sense check.** Read the JP. Does the literal proposition make
   sense in the world? (`本は静かです` — books don't have a faculty of
   being silent. `月も雨を見ます` in a clear-sky story — there is no
   rain to look at. Both fail this check.) If it fails, **rewrite
   before reviewing**, do not approve and "leave a note".
2. **Gloss faithfulness.** Cover the JP and read only the
   `gloss_en`. Then uncover the JP. Does the gloss describe what is
   actually written? Look for invented verbs ("open", "prepare",
   "leave ready") that have no corresponding token. If the gloss
   adds, drops, or changes meaning, **rewrite the gloss**.
3. **Word_id integrity.** For every content token, the `word_id` must
   identify the actual lemma the surface form derives from. If you
   are tempted to "borrow" a nearby word_id to smuggle in a verb that
   isn't in vocab, **stop**: refuse the story (Section 7) instead.
4. **Continuity.** Time of day, weather, location, and props
   established in s0–s2 must be respected by every later sentence.
   No moon at breakfast, no rain in a stars-only story.
5. **Repetition with the previous story.** If your draft repeats the
   *previous* story's opener template, location, or closer
   ("〜、いい朝です"), it is **not original** — score originality 2
   regardless of how clean the prose is, and rewrite.

A reviewer who waves a story through with "small note: a bit
repetitive" while scoring 4s is **not doing the job**. The score
must reflect the failures the prose actually has, even when the
reviewer is also the author. Especially then.

## Output

Write your review to `pipeline/review.json` with this shape:

```json
{
  "story_id": 4,
  "scores": { "hook": 4, "voice": 4, "originality": 3, "coherence": 5, "closure": 4 },
  "average": 4.0,
  "approved": true,
  "suggestions": [
    { "what": "swap s2 and s3 to delay the noun reveal", "why": "hook + coherence" },
    { "what": "drop the explicit 私は in s5 — clear from context", "why": "voice" }
  ],
  "notes": "Optional free-form prose. Anything you want a future reviewer to know.",
  "reviewer": "rovo-dev",
  "reviewed_at": "2026-04-22T01:13:00Z"
}
```
