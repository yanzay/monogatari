# Engagement Review — prompt for the human (or LLM) reviewer

You are reviewing a Monogatari story **after** the strict validator has
accepted it. The validator only proves the story is *legal* (vocabulary,
grammar, length, etc.). Your job is to ask whether the story is
**worth reading** — whether it has voice, originality, and a small
emotional truth — within the brutally narrow vocabulary the learner
currently has.

This stage is the last gate before the story ships. If you would not
re-read this story tomorrow, send it back.

## Constraints to keep in mind

- Vocabulary is severely limited (often <30 words). The author cannot
  reach for richness; they must imply it.
- Grammar is incremental. The same particle may appear five times.
- Stories are short — usually 5–8 sentences.
- Themes must be neutral / cozy / observational. No violence, romance,
  politics. Stick to weather, food, animals, the apartment, the park,
  small daily moments.

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
  "reviewer": "human:yanzay" or "llm:gpt-5",
  "reviewed_at": "2026-04-22T01:13:00Z"
}
```
