---
name: monogatari-author
description: >
  Author a Monogatari graded-reader Japanese short story end-to-end. Use when the user
  says "author story N", "write the next story", "draft story X", "monogatari author",
  or any variant of "make a new story for the corpus". Runs the full v2 gauntlet
  (palette → spec → build → lints → validate → ship) and recovers from each failure
  category without further prompting. Produces stories that satisfy ALL deterministic
  validators by construction. Aim is: user types two words, agent ships a story.
---

# Monogatari Author Skill

You are the v2 LLM author for the Monogatari graded-reader corpus. The user
should never have to explain the rules. They should be able to type `author
story N` and get a shipped story. Everything below is the *complete*
procedure — read it once, follow it.

## 0. Activation

Trigger phrases: "author story N", "author next story", "write story N",
"draft story N", "new story", "monogatari author", "make a story", or any
variant. If the user says only `author` with no number, default to "next"
(= max(existing story id) + 1).

### 0.0 The full ordered procedure (READ EVERY ACTIVATION; do not skip)

The activation summary that an agent skims often stops at "Step F —
Ship," producing the recurring failure mode where §B.0, §B.1, §E.5,
§E.6, §E.7 are silently skipped because they are subsections inside
§2 rather than top-level steps. They are NOT optional and they are NOT
covered by the gauntlet. The complete ordered procedure for ANY ship
is exactly:

1. **§A** — get the brief (`author_loop.py author N --brief-only`).
2. **§A.5** — internalize the seed plan (stories 1–10).
3. **§B** — choose intent + scene_class + anchor (in head).
4. **§B.0** — write the **PREMISE CONTRACT** into the spec's `intent`
   field, in English, with all six fields filled crisply. If you can't
   fill a field, the premise is too weak — restart §B. **REQUIRED.**
5. **§B.1** — run `pipeline/tools/forbid.py N` and paste the SUMMARY
   block under a `FORBIDDEN THIS STORY:` heading inside the spec's
   `intent`, then satisfy ALL four zones (or burn one §G override).
   **REQUIRED.**
6. **§B.2 / §C / §C.1–§C.4** — narrative coherence checklist, mint
   budget, draft sentences with would-mint, self-audit.
7. **§D** — write the bilingual spec.
8. **§E** — run the gauntlet dry-run; iterate to `would_ship`.
9. **§E.5** — write `.author-scratch/prosecution_N.md` (the structured
   prosecutor table); re-read it; ANY contract row = N → discard.
   **REQUIRED.**
10. **§E.6** — read the EN glosses of stories N, N-1, N-2 only; write
    the one-sentence "what is materially different about EVENTS"
    answer; check for escape-hatch language. **REQUIRED.**
11. **§E.7** — delegate the fresh-eyes subagent review to a fresh
    Explore subagent. SHIP / REWRITE-SENTENCE / REWRITE-STORY.
    **REQUIRED.**
12. **§E.8** — round-trip cap: max 3 §E↔§E.5/E.6/E.7 loops; escalate
    on the 4th.
13. **§F** — live ship (`author_loop.py author N`). Pytest sweep.
14. **§F.3** — auto-commit and push (per standing user directive).
15. **§F.4** — verify spec/artifact drift; fast-follow commit if drift.
16. **§G** — final report; record `overrides_used: <count>/1`.

**If you skipped any of §B.0, §B.1, §E.5, §E.6, §E.7 on a ship, you
violated the discipline. Backfill the missing artifacts (write the
prosecution table post-hoc, run the subagent post-hoc, etc.) and log
the procedural lapse in `.author-scratch/prosecution_N.md` so the
audit trail is honest.**

The §F.2 self-audit that a naive scan of the skill suggests using
INSTEAD of §E.5–E.7 was **RETIRED 2026-04-29**. It runs after
state_updater has already minted W-IDs and is therefore too expensive
to honor. See §F.2 docstring for the explicit retirement note.

## 0.1 The current authoring contract (read first if cold-starting)

The full design constraints for stories 1..10 live in
**`docs/phase4-bootstrap-reload-2026-04-29.md`**. Read it before
authoring any story 1..10. The brief surfaces the load-bearing
fields (`hard_limits.ladder`, `must_hit.seed_plan`,
`must_hit.scene_affordances`) but the doc has the full rationale,
the validation gates, and the cascade procedure.

For stories 11+ the legacy steady-state policy applies (1 grammar /
3–5 vocab per story; no scene constraint).

## 1. Hard invariants (never violate, no exceptions)

1. **NEVER edit `stories/story_N.json` directly.** That file is built. The
   only editable artifact is `pipeline/inputs/story_N.bilingual.json`.
2. **NEVER bypass `pipeline/author_loop.py`.** It is the only sanctioned
   path to ship a story. If you find yourself running `text_to_story.py`,
   `regenerate_all_stories.py`, or `validate.py` directly to "test" a draft,
   stop and use `author_loop.py author N --dry-run` instead.
3. **Vocabulary is derived from stories, not the other way around.**
   You do NOT list new words up-front. You declare a *mint budget*
   (count + conceptual neighborhood), draft against the existing palette,
   and let the new words emerge from what you actually wrote. The
   `state_updater` auto-mints on ship; `would-mint` is a *count check*
   not an existence gate. The exception is **story 1** (cold start), where
   the seed must be declared first because there is no prior corpus.
4. **NEVER add words/grammar above the current tier.** Words must be in
   the palette OR within the mint budget. Grammar points must be in the
   current tier (Check 3.5 will block cross-tier introductions). Before
   adding any verb to a draft, **also check the grammar its construction
   uses** — e.g. `言います` looks N5 but `「X」と言います` is N4 (G028).
5. **NEVER touch `data/vocab_state.json` or `data/grammar_state.json`
   directly.** Only `state_updater` modifies them, only at ship time.
6. **EVERY post-bootstrap story (story 4+) must introduce ≥1 new
   grammar point** until the current JLPT tier (and all earlier
   tiers) are fully covered by the catalog. The brief's
   `grammar_introduction_debt.must_introduce` flag tells you when
   this rule fires; the gauntlet's `coverage_floor` step and
   validator Check 3.10 hard-block any story that violates it. The
   only way out is to actually pick a new point from
   `grammar_introduction_debt.recommended_for_this_story` and weave
   it in. Tier advancement (e.g. story 11 → N4) is gated by Check
   3.9 — cannot enter the next tier while the previous one has
   uncovered points.

## 2. The procedure (the entire flow)

Use `update_todo` to track these steps for any story request. Each step
maps to a single tool call or short tool sequence.

### Step A — Get the brief (1 tool call)

```bash
source .venv/bin/activate && python3 pipeline/author_loop.py author N --brief-only
```

This emits the JSON `agent_brief` for story N. Read it. The brief contains:
- `size_band` — sentence count + content-token target
- `mint_budget` — `{min, max, target}` cap on new words this story may
  introduce. The gauntlet HARD-FAILS if `len(new_words) > max`.
- `palette.categories` — every available word grouped by sense (★ = due,
  ★★ = critical-debt; prefer star-tagged words)
- `grammar_points` — every available grammar point
- `grammar_introduction_debt` — **READ THIS BEFORE drafting.** Tells you
  which JLPT-tier catalog points are still uncovered and which are
  prereq-ready. Fields:
    * `must_introduce: bool` — if true, this story MUST add ≥1 new
      grammar point (or `coverage_floor` and validator Check 3.10 will
      hard-block the ship).
    * `current_jlpt` / `current_tier_window` — your tier ladder.
    * `coverage_summary` — `{N5: {covered, total, remaining}, …}`.
    * `recommended_for_this_story` — top 3 prereq-ready picks with
      `catalog_id`, `title`, `short`, and `examples`. **Alphabetic
      ordering caveat:** the list is currently sorted alphabetically,
      not pedagogically. Foundational picks like `N5_desu` (です),
      `N5_ka_question` (か), `N5_mashita_past` (ました), `N5_masen` may
      not be at the top even though they're the most natural earliest
      additions. Always scan the full `uncovered_in_current_tier` list
      before committing to a recommended pick.
    * `earlier_uncovered` — points from PRIOR tiers that should never
      have been skipped; if non-empty, address them first (they'll
      block tier advancement via Check 3.9).
- `grammar_reinforcement_debt` — Lists every grammar point intro'd in
  the last W stories that still needs reinforcement. Items with
  `must_reinforce: true` MUST appear in this story; the gauntlet's
  `pedagogical_sanity` step blocks if you skip them. Each item ships
  with an `example.surface` showing a concrete construction you can
  adapt.
- `must_hit.grammar_introduction.recommended` — **The first item is
  the default pick.** Recommendations are ranked by leverage score
  (direct unlocks + paradigm bonus + earlier-tier bonus); see
  `default_pick_policy` in the brief and `grammar_progression.PARADIGM_ANCHORS`
  for the curated paradigm-anchor list. Each recommendation ships with
  a `priority_rationale` string explaining why it scored where it did
  (e.g. "unlocks 13 downstream points; anchors a foundational paradigm
  (score 18)"). **Use recommended[0] unless the story's premise makes
  a different choice clearly more natural** — and if you swap to
  recommended[1] or [2], document the deferral in the spec's `intent`
  field. Do NOT pick a low-scoring leaf point (e.g. an interrogative
  like 誰 or いつ) just because it's easier to land — that's curriculum
  drift, and the post-ship coverage report will show the foundational
  unblocker still missing.

- `must_hit.word_reinforcement` — **READ THIS BEFORE drafting.** Every
  word intro'd in the immediately previous story that still needs
  reinforcement. Items with `must_reinforce: true` MUST appear in this
  story (per Rule R1, `test_vocab_words_are_reinforced`); the gauntlet's
  `vocab_reinforcement` step hard-blocks if you skip them. The brief
  shows `intro_in_story`, `lemma`, and `stories_since_intro` for each.
  Distinguish from `must_hit.word_palette_debt`, which is the long-tail
  ★/★★ list (informational, not load-bearing for the next ship).
- `north_stars` — the era's 1–3 voice templates (this is the tone you must match)
- `previous_3_stories` — what the prior corpus just did (avoid repeating motifs)
- `previous_closers` — the literal closer of the last 3 stories. Do NOT
  echo their structure; vary openings AND endings.
- `lint_rules_active` — the 10 rules your spec must pass
- `anti_patterns_to_avoid` — the 5 audit defects with bad/fix examples

**Internalize the north_stars, anti_patterns, `must_introduce`,
AND `must_reinforce` items before drafting a single sentence.** Do
not skim them.

### Step A.5 — Read the seed-plan slot for stories 1..10 (no tool call)

If story_id is in the bootstrap window (1..10), the brief's
`must_hit.seed_plan` field carries a prescriptive plan for this
slot:
  * `scene_class` — the planned scene; default for the slot
  * `intent_seed` — a 1–2 sentence prose seed for the spec's intent
  * `anchor_object_candidates` — 2–3 candidate anchors for the slot
  * `characters_min` — minimum number of distinct characters
  * `vocab_seed` — the prescribed lemmas this slot must mint (the
    ladder enforces the COUNT bound; this prescribes the IDENTITY of
    the mints)
  * `grammar_seed` — the prescribed catalog ids this slot must intro
  * `rationale` — why these specific picks

The seed plan is the single most important thing to internalize
before drafting in the bootstrap window. It is what prevents the
"warm egg on a road"-class divergence from the planned ladder. If
you must deviate from the seed plan (e.g. swap a lemma because the
scene needs something the seed missed), burn one of the session's
§G overrides and document the swap in the spec's `intent`
paragraph. Do NOT silently substitute lemmas — the count tests will
still pass but the next story's slot will then be drawing from an
unseeded vocabulary.

For stories 11+ the seed plan is empty; fall through to Step B.

### Step B — Choose intent and anchor (no tool call; in head)

Before writing JP, decide three things and write them down briefly:

1. **`intent`** (1–2 sentences): what story is this? Why does it earn its
   slot? "Two friends meet in a station and one gives the other a small gift"
   beats "morning observations about the rain."
2. **`scene_class`** (one of): `home_morning`, `home_evening`, `walk`,
   `station`, `park`, `indoor_meal`, `bookstore`, `garden`, `bedroom_night`,
   `street_dusk`, etc. **Do NOT pick a scene_class used in the previous 3
   stories** unless you have a specific reason.
3. **`anchor_object`**: the one concrete thing the story rotates around
   (a key, a letter, a bowl, a chair, a photograph). The anchor must
   appear in ≥3 sentences, ideally with a verb attached (placed, opened,
   carried, given), not as decoration.

If you cannot answer these three crisply, the story will fail. Restart.

#### Step B.0 — Premise contract (THE EARLY-BINDING CONTRACT)

**Why this exists.** Audit 2026-04-29 found that the v2 corpus had
converged on essentially one story (small-object-anchor, walk-or-room,
narrator picks up the object) for 10 consecutive ships. The §F.2
self-review at the end of the gauntlet was supposed to catch this and
didn't, because by the time it ran the agent had spent ~30 iterations
on the story, the gauntlet was green, and the cost of "discard" felt
prohibitive. The fix is to bind the discard criteria BEFORE drafting,
so the prosecutor pass at §E.5 is judging against a written contract,
not against post-hoc taste.

Before writing a single JP token, paste a **premise contract** into
the spec's `intent` field, in English. The contract has six fields:

```
PREMISE CONTRACT (story N)
  one_sentence_event:    <subject> <action verb> <object> because <reason>.
  change_of_state:       at s0 the world has X; at closer the world has Y; X≠Y.
  scene_novelty_claim:   "I am NOT writing a {prev scene_class} story
                         because the last 3 were."  (or honest exception:
                         "I AM, because <reason that will survive a hostile
                         re-read>.")
  anchor_novelty_claim:  "Anchor is <X>. <X> last appeared in story <N or never>."
  closer_shape_claim:    "Closer shape: <action|dialogue|sensory beat>. NOT
                         a noun-pile, NOT a 「Nは Adj です」 mirror of stories
                         <prev_3>."
  why_not_filler:        in 1 sentence per character/object, why does each
                         EARN its slot? (a character that only "looks" with
                         the narrator is filler; an object that only gets
                         "held" is decoration)
  obligations_absorbed:  must-reinforce <wid…>, must-introduce <gid>; how
                         each is metabolized by the premise (NOT "bolted
                         on at s4")
```

The contract is the discard criterion. **Once written, you may not
soften it after drafting.** §E.5 (the prosecutor pass) will check the
finished story against this exact text. If a field cannot be filled
crisply, the premise is too weak — restart Step B with a different
intent. Do not paper over a weak premise with prettier sentences.

#### Step B.1 — Forbidden zones (mechanical, NOT subjective)

**Why this exists.** The brief's `previous_3_stories` and
`previous_closers` fields surface recent stories as raw text, which an
LLM author tends to pattern-match into "I'll do something similar."
The audit found `motif_rotation_lint`'s 3-story window was both too
narrow AND not actually consulted in practice. Mechanical zones with
explicit forbidden values bind harder than vibes.

Run:

```bash
source .venv/bin/activate && python3 pipeline/tools/forbid.py N
```

This prints four forbidden zones for story N:
- `scene_class` used in the last 3 stories
- `anchor_object` used in the last 5 stories
- opening token sequences (first 3 content tokens of s0) of the last 3 stories
- closer morphological shapes (e.g. `noun-WA-iadj-DESU`) of the last 3 stories

**Paste the SUMMARY block verbatim into the spec's `intent` field**,
under a `FORBIDDEN THIS STORY:` heading, immediately below the premise
contract from §B.0. Then satisfy them ALL.

If a forbidden value is unavoidable (e.g. a must-reinforce word IS the
forbidden anchor of story N-1), you may take a deliberate exception —
but it counts toward the per-session **override budget** (§G; max 1
override per session). Document the override in the spec's `intent`:
```
  OVERRIDE: anchor_novelty_claim violated because <wid> is must_reinforce
  from story N-1 and the only sane host sentence makes it the anchor.
  Mitigation: <X>.
```

`forbid.py` is purely descriptive — it never edits files, never blocks.
The discipline is yours; the tool just supplies the facts.

#### Step B.2 — Narrative coherence checklist (THE LITERARY CONTRACT)

Lints catch nonsense sentences. They cannot catch a story that is
structurally correct and narratively dead — the "checklist-driven
storytelling" defect that produced 56 v1 stories that mostly passed
machine checks but read as observational filler. Before writing a
single sentence, you MUST be able to answer YES to all five:

1. **What changes between sentence 1 and the closer?** If the answer is
   "nothing of consequence" — the narrator observed something, then
   observed it again — the story is observational filler. Restart with
   a real change of state.
2. **Where does each character enter the scene?** If a character appears
   mid-story, they need an entrance sentence (the door opens, footsteps
   in the hall, a call from the kitchen). Otherwise they teleport, and
   the reader stops to ask "wait, where did they come from?" Solitary
   scenes are FINE. Mixed scenes need staging.
3. **What does the anchor object DO?** It must satisfy the **object
   causality test** — at least ONE of:
     - Change owners (be given/received).
     - Change state (be opened/closed/broken/cooked/written/torn).
     - Change location meaningfully (not "I hold it then I still hold it").
     - Trigger an action by a character.
   If your anchor only gets *looked at* and *held*, it is decoration,
   not an actor. Pick a different anchor or a different verb.
4. **Does every character have a purpose?** A second character must
   force dialogue, action, or a transfer. A friend who only "looks
   along with the narrator" is grammar-bait, not a character. If a
   `must_reinforce` obligation pulled a character on stage, see the
   pedagogical-vs-narrative tension rule (§3a) — DO NOT just bolt them on.
5. **Read the spec aloud in your head: "What happens in this story?"**
   The answer must be a sentence with a verb of action, transfer, or
   change. If the answer is "I observe X" or "I notice Y," the story
   has no arc. Restart.

If any of the five fails, do not write the spec. Iterate the intent
until they all pass.

### Step C — Declare a mint budget, then draft against the palette

**Mint budget = (count, neighborhood).** Before drafting, decide:
- **Count:** how many new words this story may introduce. Defaults:
  story 1 = 10–16, stories 2–5 = 2–5, stories 6–15 = 1–4, stories 16+ = 0–3.
- **Neighborhood:** what conceptual area the new words belong to (e.g.
  "verbs of giving/receiving", "weather words", "body parts"). Make this
  match the story's intent. Random new words = curriculum drift.

Then draft the story freely against `palette + budgeted mints`. Use
`would-mint` per candidate sentence to **count** new words minted so far,
not to gate them:

```bash
source .venv/bin/activate && python3 pipeline/tools/vocab.py would-mint "<候補の日本語>"
```

If your running mint count exceeds the budget, either replace mints with
palette words OR explicitly raise the budget (and explain why in the spec
`intent` field). Do NOT silently mint over budget — the post-ship
validator will block it.

**For each new mint you DO want, also run a grammar check:** does this
verb's standard construction (te-form, ています, と quotative, etc.) require
a grammar point above the current tier? If yes, defer the verb to a
later story.

> **Implementation note (updated 2026-04-28):** the gauntlet now
> enforces the mint budget at the `mint_budget` step — exceeding the
> brief's `mint_budget.max` is a hard fail. Use `would-mint` per
> sentence to keep a running count; if you have to exceed the cap,
> document the reason in the spec's `intent` field AND stop to ask
> the user before shipping.

#### Step C.1 — The reflection slot rule

A `reflection` role MUST add information not already on the page. Banned:
restating an attribute already established in setting (e.g. setting says
「小さい卵」, reflection says 「卵は小さいです」 — that's restatement, not
reflection). Encouraged: a comparison to something else, a sensory
detail not yet named (weight, temperature, sound, smell), the narrator's
relation to the object (familiarity, confusion, recognition).

Quick test: cover the reflection sentence with your hand. Re-read the
story without it. If nothing of substance is lost, the reflection was
filler. Cut it or rewrite it to add real information.

#### Step C.2 — Closer cliché ladder

The previous_closers field in the brief shows you the literal last 3
closers. Your closer must NOT structurally mirror any of them — varying
the noun in a fixed template counts as mirroring. The current banned
templates (after stories 1, 2, 3):

- `[X]は[Y]を[Z]に持ちます` — "[someone] holds [object] in [their] hand."
  Used by stories 1, 2, 3. **Banned for stories 4–8.**
- `[X]は[Y]を見ます` — "[someone] looks at [object]" as a closer.
  Mostly observational; banned unless paired with a real change of state.
- `[X]は「Z」と言います` — likely the next cliché when dialogue arrives.
  Pre-rotate: limit to once per 3 stories.

Pattern bank for fresh closers (use one, then retire it for a few stories):
- Sustained dialogue line: `友達は「ありがとう」と言います`. (When dialogue
  is in tier.)
- Departure: `友達は道を歩きます` (the friend walks away — anchor stays).
- Settling: `卵は机の上にあります` (the object comes to rest somewhere new).
- Relational beat: `友達は私の手を見ます` (a character notices the narrator,
  not the anchor — flips the gaze).
- Sensory closer: `雨の音が聞こえます` (a sense beat that wasn't on stage).

#### Step C.3 — Pedagogical-vs-narrative tension

When `grammar_reinforcement_debt` lists a `must_reinforce: true` item,
you have THREE legitimate ways to satisfy it:

(a) **Native fit**: the construction is already implied by your story's
    intent. (E.g. you already planned a two-character scene; companion-と
    falls out naturally. Best.)
(b) **Pay the scenic cost**: rewrite the intent so the construction has
    a real reason to be there. Add an entrance sentence; rebuild the
    arc around the new character. (Acceptable, but expensive — usually
    means restarting Step B.)
(c) **Defer**: skip this story for the obligation; satisfy it in story
    N+1. Document the deferral in the spec's `intent` field
    ("deferring G010_to_and reinforcement to story N+1 because the
    intent requires a solitary scene"). The brief's `must_reinforce`
    test will fire for story N+1, so YOU MUST then carry it.

**FORBIDDEN**: jamming the must-reinforce surface into a sentence that
contradicts the story's premise (e.g. teleporting a friend into a
solitary scene to land 友達と). The lints will pass; the story will be
broken. The whole point of the agent-author architecture is that the
deterministic checks are necessary but not sufficient — the literary
contract is yours to honor.

If you find yourself doing (b) and the rewrite gets ugly, choose (c).
Deferring one story is cheap; shipping a teleporting-friend story is
expensive (it cements the defect into the corpus).

#### Step C.4 — Self-audit before Step E

After writing the spec, before running the gauntlet, do a 60-second
self-audit:

1. Read the spec aloud (in head). What's the one-sentence summary of
   what HAPPENS? "X gives Y to Z" / "X opens Y and finds Z" / "X waits
   for Y; Y arrives" — concrete and verb-driven. If the summary is
   "X observes Y" or "the scene is quiet," restart.
2. Look at sentences 0 and last side by side. Has anything *changed*?
   (location of object, possession, character on stage, time of day,
   the narrator's understanding.) If no, restart.
3. Cover each sentence in turn. Is anything lost when it's gone? If a
   sentence is removable without consequence, it's filler — rewrite or cut.
4. Check the closer against the cliché ladder (§C.2). If it mirrors any
   previous closer, rewrite.

Only when these four pass do you run Step E. The cost of a restart
here is one drafting iteration; the cost of shipping a defect is
permanent corpus pollution.

Per-sentence requirements:
- Declare a `role`: `setting | action | dialogue | inflection | reflection
  | closer`. The story must contain at least one of {action, dialogue,
  inflection} — pure observation strings will fail Step E.
- The closer (last sentence) **MUST have a verb other than the final
  copula**. A closer like 「雨の朝、猫や花、静かな窓です。」 is the canonical
  v1 defect and will fail lint 11.7.
- Avoid the 5 anti-patterns from the brief. Memorize them:
  - **tautological-equivalence**: 「XのY は ZのY です」 (e.g. cat's color
    = rain's color). Use a concrete adjective instead.
  - **closer-noun-pile**: noun lists + です with no verb.
  - **bare-known-fact**: 〜と思います on a fact you already asserted.
  - **misapplied-quiet**: 静か / 静かに on inanimate objects (book, letter,
    egg, chair). Reserve 静か for places (rooms, streets) and animate
    subjects.
  - **decorative-noun**: a scene noun appearing once with no payoff.

### Step D — Write the bilingual spec (1 tool call)

Write to `pipeline/inputs/story_N.bilingual.json`. The required v2 schema:

```json
{
  "story_id": N,
  "title": {"jp": "...", "en": "..."},
  "intent": "<from Step B>",
  "scene_class": "<from Step B>",
  "anchor_object": "<from Step B>",
  "characters": ["narrator", "..."],
  "sentences": [
    {"jp": "...", "en": "...", "role": "setting"},
    {"jp": "...", "en": "...", "role": "action"},
    ...
    {"jp": "...", "en": "...", "role": "closer"}
  ]
}
```

If the story_N.bilingual.json already exists from a prior attempt, **back
it up to `/tmp/` first** before overwriting:

```bash
cp pipeline/inputs/story_N.bilingual.json /tmp/story_N.bilingual.json.bak
```

### Step E — Run the full gauntlet (1 tool call) AND iterate to green FIRST

```bash
source .venv/bin/activate && python3 pipeline/author_loop.py author N --dry-run
```

This runs: spec_exists → agent_brief → build → validate (incl. all 10
lints AND Checks 3.6/3.9/3.10 grammar coverage) → mint_budget →
pedagogical_sanity (grammar reinforcement) → vocab_reinforcement (R1
must-reinforce words) → coverage_floor (grammar introduction)
→ would-write → audio (skipped on dry-run;
real on live ship).

**Iterate to green BEFORE running the literary review.** If the dry-run
fails, see §3 (failure recovery), edit the spec, and re-run the gauntlet
until `VERDICT: would_ship`. The prosecutor pass (§E.5) and the
fresh-eyes subagent (§E.7) are EXPENSIVE and must run only against text
that is already correctness-clean — running them against drafts that
later get rewritten by the gauntlet wastes the review and ships defects
that the rewrites silently introduced.

> **Ordering postmortem (2026-04-29):** an earlier version of this
> skill ran §E.5/E.6/E.7 *before* the gauntlet, on the assumption that
> the literary review should bind the discard criteria as early as
> possible. This was a real bug: when the gauntlet then forced a
> sentence rewrite (lint 11.x fix, mint trim, grammar swap), the
> prosecutor's verdict was on text that no longer existed, and the
> rewritten text could ship with literary defects the prosecutor never
> saw. The cheap correctness step runs FIRST as a filter; the
> expensive literary step runs SECOND on the survivor. If the literary
> step then forces a sentence edit, you bounce BACK to the gauntlet
> (see §E.8 round-trip cap) — the loop only exits when both
> correctness AND literary are green on the SAME text.

**Once `VERDICT: would_ship`, proceed to §E.5.** Do NOT skip to §F.

> ⛔ **STOP — DO NOT RUN `author_loop.py author N` (live ship) NEXT.**
> The next steps are §E.5, §E.6, §E.7. They are REQUIRED, not optional.
> The gauntlet's `would_ship` verdict is a *correctness* verdict, not a
> *literary* verdict. The literary contract (§B.0) is checked here, by
> hand, in `.author-scratch/prosecution_N.md`, and by a fresh-eyes
> subagent (§E.7). Skipping §E.5/E.6/E.7 ships convergence defects that
> the gauntlet is structurally incapable of catching. If you ever find
> yourself reading "Step F" right after this line without having first
> created `.author-scratch/prosecution_N.md`, you've slipped — go back.

### Step E.5 — Prosecutor pass (ONLY after §E is green; re-run after every gauntlet iteration)

**Why this exists.** A green dry-run says the story is technically
valid, not that it is good. The audit found that 8 of 10 stories had
shipped with a green gauntlet despite being structurally identical to
the previous one. The prosecutor pass forces a structured, written
critique against the §B.0 contract — written to a file in
`.author-scratch/` (NOT `/tmp/` — the workspace doesn't permit `/tmp`),
then re-read — so I can't soften "no" into "yeah but" inline.

**The freshness rule.** §E.5 must run against the text that came out of
the most recent green gauntlet iteration. If you have to bounce back to
§E (re-run gauntlet) after this step for any reason — including because
§E.5 itself forced a sentence edit — you MUST re-run §E.5 against the
new text. The prior verdict is invalidated by ANY sentence-level edit.
The only carryover exception is the trivial-edit rule in §E.8.

After Step E reports `would_ship`:

1. Open `pipeline/inputs/story_N.bilingual.json` and re-read the spec
   AS A HOSTILE CRITIC whose only job is to argue against shipping.
2. Write a structured table to `.author-scratch/prosecution_N.md` (use
   `create_file`). NOTE: the workspace forbids writes to `/tmp/`; use
   the in-workspace scratch dir. The table has one row per sentence
   plus four contract rows:

```markdown
# PROSECUTION — story N

| sentence | role | could I delete it and lose nothing? | concrete-physical verb? | object load-bearing? |
|---|---|---|---|---|
| s0 | setting | Y / N + reason | — | — |
| s1 | action  | Y / N + reason | Y / N | Y / N |
| …  |         |                |       |       |
| closer | closer | matches §B.0 closer_shape_claim? Y/N | mirrors prev 3? Y/N | — |

## Contract checks (against §B.0 PREMISE CONTRACT)

| field | honored? | concrete evidence (sentence id + surface) |
|---|---|---|
| one_sentence_event   | Y / N | … |
| change_of_state      | Y / N | s0 = …, closer = …, X≠Y? Y/N |
| scene_novelty_claim  | Y / N | … |
| anchor_novelty_claim | Y / N | … |
| closer_shape_claim   | Y / N | … |
| why_not_filler       | Y / N (per row) | … |
| obligations_absorbed | Y / N | … |
```

3. Re-open `.author-scratch/prosecution_N.md` and READ IT. The cells
   are Y or N. "Yeah but" / "technically Y because…" answers are **N
   for the purposes of this gate.**
4. **Decision rule:** ANY contract row = N → **discard, restart from
   Step B with a different premise.** Do NOT just tweak sentences;
   §B.0 is a premise discard, not a sentence discard. Per-sentence
   rows = N (deletable / non-physical / non-load-bearing) → fix that
   sentence, BOUNCE BACK to §E (re-run gauntlet to confirm the edit
   didn't break anything), and re-run §E.5 on the new text. If you
   can't fix it without breaking the contract, also discard.

The scratch file persists across this session; if a subagent audits the
session later it can see the verdict you committed to before the ship.
The `.author-scratch/` directory is gitignored-by-convention; do NOT
commit prosecution tables (they're working notes, not artifacts).

### Step E.6 — Two-blind-readings comparison (cheap; kills sameness)

**Why this exists.** The mode of failure the prosecutor pass is
weakest on is "this is technically a different story but materially
identical to the last one." Reading EN-only blocks the JP-attentional
context that makes me say "but the grammar is different!"

**Freshness rule (same as §E.5):** §E.6 runs ONLY after §E is green
AND §E.5 returned SHIP. Any subsequent sentence edit invalidates the
prior §E.6 verdict — re-run on the new text.

Read **only the English glosses** of stories N, N-1, N-2 in order
(use `open_files` on `pipeline/inputs/story_{N,N-1,N-2}.bilingual.json`
and look at the `en` fields only — ignore `jp`, ignore everything
else). Then write one sentence answering:

> "What is materially different about the EVENTS of story N compared
> to N-1 and N-2?"

If your sentence uses any of these escape hatches, it is a discard
signal:
- "the anchor is a different object" (anchor identity ≠ event difference)
- "the scene_class is different" (scene ≠ event)
- "the grammar point is different" (pedagogy ≠ event)
- "the mood/tone is different" (tone ≠ event)

Acceptable difference vocabulary: discovers, transfers, refuses,
chooses, fails, surprises, breaks, finishes, decides, declines,
reveals. Verb of action/transfer/discovery, per §B.0.

If you can't write the sentence without escape hatches → discard.

### Step E.7 — Fresh-eyes subagent review (1 tool call)

**Why this exists.** Same model + same context = same blind spots.
Same model + DIFFERENT context (no priors, no drafting state) gives
sufficiently independent judgment to catch what I missed. AGENTS.md
("Parallel subagents are great for…") records this pattern working
already.

**Why the prompt is structured the way it is.** A user audit on
2026-04-29 found the prior §E.7 prompt ("What HAPPENS?", "Did
anything surprise you?", "SHIP / REWRITE-SENTENCE / REWRITE-STORY")
was rubber-stamping technically-valid stories that read as bolted-
together obligation lists (story 4 — "私の名前" — passed §E.7 SHIP
despite a teleporting friend with no entrance, an arbitrary "no
pencil" assertion to satisfy arimasen-reinforcement, and a
3-token classroom "transfer" with no emotional weight). The problem
was prompt-shaped: "what happens" only asks for a verb-bearing
sentence (which a checklist of pedagogical sentences trivially has),
and "did anything surprise you" lets a polite reader default to
"no." The replacement prompt below briefs the subagent as a
**hostile reviewer**, names the **specific failure modes** to hunt
for, and **biases the default verdict to REWRITE** so SHIP must be
positively earned, not passively accepted.

**Freshness rule (same as §E.5/E.6):** §E.7 runs ONLY after §E is
green AND §E.5/E.6 returned SHIP. The subagent reads the spec file
directly, so the spec on disk MUST be the gauntlet-green version. Any
subsequent sentence edit invalidates the prior §E.7 verdict — re-run.

Delegate to an `Explore` subagent with this **exact** task (do not
soften the framing — the hostility is load-bearing):

> "You are a HOSTILE LITERARY REVIEWER for a Japanese graded-reader
> corpus. Your job is to find reasons to REJECT this story, not to
> approve it. The default verdict is REWRITE; SHIP is only earned
> when the story survives every probe below. Polite "good enough"
> approvals have shipped defects into the corpus — do not be polite.
>
> READ ONLY:
>   - `pipeline/inputs/story_N.bilingual.json` (the candidate)
>   - `pipeline/inputs/story_{N-1}.bilingual.json`
>   - `pipeline/inputs/story_{N-2}.bilingual.json`
>   - `pipeline/inputs/story_{N-3}.bilingual.json` (if it exists)
> Do NOT read AGENTS.md, the SKILL, the brief, the corpus, or
> anything else. You must judge ONLY what is on the page in front
> of a learner.
>
> READ THE EN GLOSSES FIRST, then the JP. If the EN reads like a
> story you would want to read again, that is a positive signal. If
> the EN reads like 'sentence 1, sentence 2, sentence 3 — done' with
> no scene, no stakes, no human feel, that is the failure mode this
> review is built to catch.
>
> Then, in ≤250 words, answer ALL eight probes. Be specific (quote
> sentence ids and surface forms) — vague answers count as N.
>
> 1. ONE-SENTENCE EVENT. Write the story in one sentence using a
>    verb of action, transfer, decision, refusal, discovery, or
>    revelation (NOT "observes", NOT "is", NOT "notices"). If the
>    only verb you can honestly use is observational, that is a
>    REWRITE-STORY signal — the story has no event.
>
> 2. CHARACTER ENTRANCES. For every character other than the
>    narrator, name the sentence in which they ENTER the scene
>    (door opens, footsteps, a voice from elsewhere, a spatial
>    placement that earns its keep — 'the friend behind me' counts
>    ONLY if the spatial relationship pays off later). A character
>    who simply appears mid-story with no entrance is a TELEPORT
>    and is REWRITE-STORY-grade.
>
> 3. WHY-IS-EACH-FACT-HERE. For every assertion in the story
>    (especially negative ones — "X has no Y", "X doesn't know Y"),
>    explain in one phrase why the story would suffer if that
>    assertion were deleted. If the honest answer is "to satisfy a
>    grammar slot" or "to set up the closer mechanically", call it
>    a PEDAGOGICAL BOLT-ON. Two or more bolt-ons = REWRITE-STORY.
>
> 4. ANCHOR CAUSALITY. Name the sentences in which the anchor
>    object appears. Does the anchor (a) change owners, (b) change
>    state, (c) change location meaningfully, or (d) trigger an
>    action by a character? If the anchor only gets held / looked
>    at / mentioned, it is decoration → REWRITE-STORY.
>
> 5. CLOSER WEIGHT. Read the closer sentence aloud (in head). Does
>    it land — does it carry the emotional or narrative weight of
>    everything before it? Or is it a mechanical 'and then X
>    happened' that could have been any other action? A weak closer
>    is REWRITE-SENTENCE at minimum.
>
> 6. SAMENESS PROBE. Compare to stories N-1, N-2, N-3. Note any
>    repetition of: anchor TYPE (small portable object vs. fixed
>    feature vs. food), event SHAPE (narrator-acts-on-object,
>    object-changes-hands, character-arrives, character-departs),
>    sentence RHYTHM (every sentence is subject-particle-object-
>    verb with no variation), closer TEMPLATE (X-が-Y / X-は-Y-を-V
>    / X-は-Y-に-Z-を-V). Three+ sames = REWRITE-STORY.
>
> 7. THE LEARNER TEST. Imagine a JLPT N5 learner reading this in
>    week 4 of self-study. Do they (a) feel they have READ A STORY
>    today, (b) feel they have done a GRAMMAR EXERCISE today, or
>    (c) feel confused? Only (a) is SHIP. (b) is REWRITE-STORY —
>    the v2 corpus's whole reason to exist is to NOT be (b).
>
> 8. THE 'WOULD I WRITE THIS' TEST. If a human author who had been
>    paid to write a literary children's vignette around the
>    available vocabulary handed YOU this draft, would you accept
>    it or send it back? Send-back = REWRITE.
>
> VERDICT (one of three; the default is REWRITE):
>   - SHIP — only if probes 1–8 all return positive signals AND you
>     can honestly say 'this is a story, not a worksheet'.
>   - REWRITE-SENTENCE — name the offending sentence(s) and the
>     specific defect in one line each. Use this ONLY when the
>     story is fundamentally sound and 1–2 surgical edits would
>     fix it.
>   - REWRITE-STORY — the premise itself is the problem (no event,
>     teleporting characters, decoration anchor, two+ bolt-ons,
>     learner-test fails). Recommend a different premise direction
>     in one sentence.
>
> If you find yourself wanting to write 'mostly fine' or 'good
> enough' or 'technically valid' — that is a REWRITE verdict
> wearing a polite mask. Strip the mask."

If the subagent says SHIP → proceed to Step F.
If REWRITE-SENTENCE → fix the named sentence, BOUNCE BACK to §E
(re-run the gauntlet — the edit may have broken correctness), and
re-run §E.5/E.6/E.7 on the new text.
If REWRITE-STORY → discard, restart Step B. Override the verdict
ONLY by spending a §G override (max 1 per session) — and document
WHY the subagent's REWRITE was wrong, sentence by sentence, in the
override note. "I disagree" is NOT a valid override; you must
identify a concrete error in the subagent's reasoning.

**Calibration check (every 5th story).** If the last 5 §E.7 verdicts
were all SHIP, suspect the prompt has been internalized as a
formality and re-deploy with a paraphrase that asks the subagent to
ARGUE FOR REWRITE explicitly first, then optionally retract. The
v2 corpus is small and the cost of one false-SHIP is permanent
pollution; the cost of one false-REWRITE is one extra drafting
loop.

Cost: ~1 tool call, ~10–15 seconds. Still cheap relative to a
shipped defect.

### Step E.8 — Round-trip cap and the trivial-edit carryover

**Why this exists.** The §E ↔ §E.5/E.6/E.7 loop can in principle
ping-pong: gauntlet says "trim a mint," I trim, prosecutor says "the
trim broke the closer," I rewrite the closer, gauntlet says "the new
closer fails lint X," etc. Without a cap, this loop can burn an entire
session. With a too-cheap cap, real defects get suppressed by
escalation fatigue.

**The cap:** at most **3 round-trips** through §E ↔ §E.5/E.6/E.7
per story. A round-trip is "gauntlet went green → literary review
forced an edit → gauntlet had to be re-run." After the third
round-trip, **stop and escalate to the user.** Surface in ≤5 lines:
what each round-trip changed, what the current blocker is, and one
proposed simplification (usually: pick a different anchor, or pick a
different grammar floor pick that makes the must-reinforce easier).

**The trivial-edit carryover.** A "round-trip" only counts when the
edit changed at least one full sentence. Pure punctuation fixes,
single-particle swaps within the same sentence, or whitespace fixes do
NOT invalidate the prior §E.5/E.6/E.7 verdicts and do NOT consume a
round-trip slot. The threshold is sentence-level: if `git diff
pipeline/inputs/story_N.bilingual.json` shows changes to a `jp` field
that altered the sentence's surface lemmas or its predicate, it's a
real edit; smaller deltas carry over.

**Hard rule on round-trip 4+:** if you ever find yourself running §E
for the fourth time on a single story, the obligations and the
literary contract are in irreconcilable tension. Escalate. Do NOT
ship a story that took 4+ round-trips even if it eventually went
green — the corpus does not need a story whose every sentence is the
result of a forced compromise. Better to defer and re-tune the seed
plan or the ladder for that slot.

### Step F — Ship (only when §E, §E.5, §E.6, §E.7 are ALL green on the SAME text)

> ⛔ **GATE.** Before running the live ship command below, confirm:
> - `.author-scratch/prosecution_N.md` exists, all contract rows = Y. (§E.5)
> - You have written down the §E.6 "materially different EVENTS" sentence
>   and it does NOT use any escape-hatch phrase.
> - The §E.7 fresh-eyes subagent returned `SHIP`.
>
> If any of those is false, do NOT run the live ship. Either complete
> the missing gate, or — if the gate FAILS — discard and restart §B.

```bash
source .venv/bin/activate && python3 pipeline/author_loop.py author N
```

(Same command without `--dry-run`.)

**The live ship now runs the full post-ship chain automatically**
(as of 2026-04-28). A single `author_loop.py author N` invocation:

1. Builds the story from the spec.
2. Runs all gauntlet checks (validate, mint_budget, pedagogical_sanity,
   vocab_reinforcement, coverage_floor).
3. Writes `stories/story_N.json`.
4. Runs `state_updater` with a plan auto-built from the build report
   (mints new W-IDs, attributes new grammar points). No hand-written
   plan JSON is required — `text_to_story` already records full mint
   metadata (surface/kana/reading/pos/verb_class/adj_class/meanings).
5. Runs `regenerate_all_stories --story N --apply` to set
   `is_new` / `is_new_grammar` flags and `new_words` / `new_grammar`
   arrays.
6. Runs `audio_builder` against the shipped story (incremental — skips
   files that already exist).

If any step fails, the gauntlet reports `halted_at: <step>` and exits
non-zero; partial state may be written to `stories/`, but `state_backups/`
captures the prior `data/{vocab,grammar}_state.json` for restore.

**You only need to verify the test suite** after a successful ship:

```bash
source .venv/bin/activate && python3 -m pytest pipeline/tests/ -q
```

#### Step F.1 — Audio is built automatically (Step F covers it)

The author_loop's `audio` step calls `pipeline/audio_builder.py` with
the just-shipped story file. Per-sentence and per-word MP3s are written
to `audio/story_N/`. The builder is incremental — re-running is cheap;
existing files with matching content hashes are skipped.

If you need to back-fill audio for older stories (e.g. a corpus that
shipped before audio was wired in), the same builder is exposed as a
standalone CLI:

```bash
# Back-fill all older stories (cheap; incremental).
for n in $(seq 1 N); do
  source .venv/bin/activate && python3 pipeline/audio_builder.py \
      --vocab data/vocab_state.json stories/story_$n.json
done
```

If the audio builder fails (network, GCP credentials, quota), STOP and
report the failure to the user; do NOT proceed to commit. Audio is part
of the shipping contract.

#### Step F.2 — RETIRED 2026-04-29 (replaced by §E.5–E.7)

The post-ship five-question gate that used to live here was retired
because it ran AFTER `state_updater` had already minted W-IDs and
attributed grammar — which made "discard" disproportionately
expensive (full state restore, audio cleanup, regenerator re-runs)
and therefore discouraged honest answers. The replacement runs
BEFORE the live ship:

- §B.0 binds the discard criteria (premise contract) before any JP
  is drafted.
- §B.1 mechanically forbids the convergence patterns the audit
  found (`pipeline/tools/forbid.py`).
- §E.5 forces a written prosecutor table against §B.0 (in
  `/tmp/prosecution_N.md`) before the ship.
- §E.6 forces an EN-only re-read against the previous 2 stories.
- §E.7 spends 1 tool call on a fresh-eyes subagent that has no
  drafting context.
- §G caps the per-session override budget at 1, so I can't quietly
  downgrade three rejections into "yeah but"s.

If §E.5/E.6/E.7 said SHIP, the ship is the ship. There is no second
post-ship review. If you want to re-read the shipped story for
spec/artifact drift, that's §F.4 — narrow, mechanical, NOT a
quality gate.

#### Step F.3 — Auto-commit and push (only if §E.5/E.6/E.7 passed)

**STANDING ORDER (user directive 2026-04-28, reaffirmed 2026-04-28
17:50): when the pre-ship discipline in §E.5/E.6/E.7 passed and the
gauntlet is green, commit AND push automatically. Do NOT ask the user
for confirmation. Asking is treated as a skill regression. The
directive is permanent and applies to ALL authoring sessions and ALL
related tooling-fix sessions, not just the session where it was
issued. The only exception is when §E.5/E.6/E.7 itself
fails — in that case do NOT commit (see "blocking conditions" below).**

Procedure:

1. `git status` + `git diff --stat` (sanity check that only the
   expected files changed — see file list below).
2. `git add` the exact set:
   - `stories/story_N.json`
   - `pipeline/inputs/story_N.bilingual.json`
   - `data/vocab_state.json`
   - `data/grammar_state.json`
   - `audio/story_N/`
   - any `state_backups/*.json` snapshots created during this run
     (vocab + grammar + `regenerate_all_stories/` subdir)
3. `git commit -m "<msg>"` with this format:
   ```
   Add story N: <title_jp> / <title_en>

   <3–5 line body: structural choice, new mints, reinforcements landed,
   any deferrals.>
   ```
4. `git push`.
5. Report the resulting commit SHA + remote URL in the §G summary.

**The ONLY conditions that block auto-commit:**

- §E.5 prosecutor pass / §E.6 EN-only re-read / §E.7 fresh-eyes
  subagent flagged a contract violation or REWRITE verdict. **The
  discard path runs BEFORE the ship** so this should never block at
  commit time — but if for any reason a story made it past §E.5–E.7
  with an unresolved REWRITE flag, do NOT commit.
- `git status` shows unexpected files modified (e.g. unrelated edits in
  `src/`, `pipeline/`). In that case, stage ONLY the story-related files
  listed above, commit those, push, and flag the stray changes to the
  user separately.
- The working tree is on a non-`main` branch the user did not ask for.
  Confirm branch context first.
- A pre-existing local commit is unpushed AND unrelated to this story.
  Push only after surfacing the situation to the user.

If the user wants to disable auto-push for a specific story, they will
say "ship but don't push" / "commit only" / similar. Otherwise: push.

#### Step F.4 — Reconcile the spec's `intent` prose with what actually shipped

**Added 2026-04-28 evening after a fresh-eyes subagent audit caught a
defect class the prior procedure had no rule for: spec/artifact drift.**

When a story goes through several rewrites in one session — closer
rotated to escape a cascade trap, mints swapped, a new sentence
inserted to satisfy must-reuse — the `sentences[]` array gets updated
on every iteration but the `intent` prose paragraph almost never does.
By ship time, `intent` describes the story you originally PLANNED to
write, not the one that actually shipped. Future agents reading the
spec (including subagent audits, future cascade-impact reviews, and
your own next-session memory) will trust the prose and be wrong about
what the corpus actually contains.

**Concrete example from this session (story 7):** the intent paragraph
claimed the closer was 「読む紙は暖かいです」 (introducing
G055_plain_nonpast_pair via a relative clause + threading the warmth
motif), but the shipped sentences[] array carried 「紙は古いです」 because
mid-rewrite the closer was rotated to escape G055's cascade-debt trap.
The prose was never updated. A subagent audit reading the spec
flagged it as REWRITE-SENTENCE on the (false) grounds that
"spec ≠ artifact."

**The rule:** After §F.3 commit-and-push completes, re-read the
spec's `intent` paragraph alongside the final `sentences[]` array.
For each load-bearing claim in the intent, verify the sentences
support it. Look specifically for:

1. **Closer surface form** — if the intent quotes a closer in 「…」,
   confirm it matches the actual closer sentence verbatim.
2. **Grammar introduction claim** — if the intent says "introduces
   N5_X" or "G0NN_…", confirm the actual `new_grammar` array in
   `stories/story_N.json` contains it (and only it, if the intent
   claims a single intro).
3. **Mint count and identity** — if the intent says "mints exactly
   K new words (W, X, Y)", confirm the `new_words` array matches.
4. **Reinforcement claims** — if the intent says "reinforces W in
   sentence S", confirm sentence S contains W.
5. **Cascade-debt claims** — if the intent says "addressed by adding
   a relative clause to story N+1", confirm story N+1's spec actually
   contains that addition. (Catches the case where the cascade-fix
   plan was abandoned mid-session.)

**If you find drift:** rewrite the intent paragraph to describe what
actually shipped. If the original plan changed for a documented
reason (cascade trap, lint failure, must-reuse insertion, etc.), add
a `HISTORICAL NOTE:` clause explaining what the original plan was
and why it was abandoned — this is more useful to future readers
than silently overwriting. The intent rewrite is text-only, never
changes the built artifact, never invalidates tests; just commit it
as a fast-follow with message `Reconcile story N intent prose with
shipped artifact`.

**If you find no drift:** skip the rewrite, but log "intent verified
matches artifact" in your §G report.

This step should be invisible to the user — they should not have to
ask for it. Treat it as part of §F's shipping contract, like audio.

### Step G — Report (no tool call; final message to user)

In ≤15 lines: ship status, the 1-line title in JP/EN, the structural
choice you made and why, the audio status (built / cached / skipped),
and the commit proposal awaiting their approval (with the exact
files staged). Do NOT repeat the entire sentence list — the user can
read the file.

## 3. Failure recovery (one playbook per failure category)

When `author_loop.py` reports `VERDICT: fail`, identify the halted_at step
and apply the matching recipe.

### Halted at `spec_exists`
Spec file is missing or malformed JSON. Re-do Step D.

### Halted at `build` with "unresolved tokens"
A token couldn't be tokenized — usually a typo or a kanji form not in the
dictionary. Run `vocab.py would-mint` on the offending sentence; the
unresolved token will be in the output. Replace with a known word.

### Halted at `build` with "new word mints over budget"
You minted more new words than your declared budget. Two recovery options:
- Trim: replace late-story mints with palette words.
- Raise the budget: edit the spec's `intent` to justify the mint count,
  then re-run. Both are legitimate; choose based on whether the new words
  serve the story's purpose or were accidental.

### Halted at `validate` with "Check 3.5 cross-tier intro"
You introduced a grammar point above the current tier (e.g. quotative-と
in story 1). The most common case: you used a verb whose natural
construction requires advanced grammar. Recovery: replace the construction
with a tier-appropriate alternative (e.g. plain assertion `いいです` instead
of `「いい」と言います`), or defer the verb to a later story.

### Dry-run passed but live ship FAILED
The dry-run validates against the *pre-ship* state; the live ship updates
state then re-validates. They can diverge for tier checks (Check 3.5) and
mint-budget checks. The state is reset automatically by `author_loop.py`
on failure, BUT freshly-shipped artifacts in `stories/` may need cleanup.
Run `git status stories/ data/` to see what changed; revert if needed.

### Halted at `validate` — Check 11 (semantic_lint)
The most common failure. The error message names the rule and quotes the
sentence. Apply the rule's `fix` from the anti-patterns table:

| Rule fired | What you wrote (probably) | What to write instead |
|---|---|---|
| 11.1 / 11.10 inanimate-quiet | 「本は静かです」 / 「本は静かに〜」 | Drop 静か; pick a real attribute (古い, 大きい, 赤い) |
| 11.2 consumption-target | 「お茶を歩きます」 sort of nonsense | Use the verb's natural object |
| 11.3 / 11.9 self-known-fact | 「夏は暑いと思います」 said in summer | Plain assertion 「夏は暑いです」, OR hedge another being's state 「猫は元気だと思います」 |
| 11.4 companion-to | misuse of と as "with" | Make sure the と-noun is animate |
| 11.5 redundant-mo | も decorating, not adding | Remove も or add the prior set |
| 11.6 location-wo | を on a noun-list of locations | Use one location with を, the others with で or に |
| 11.7 closer-noun-pile | 「雨の朝、猫や花、静かな窓です」 | Add a verb-bearing closer: action, dialogue, or single observation |
| 11.8 tautological-equivalence | 「猫の色は雨の色です」 | Concrete adjective: 「猫は白いです」 OR comparison with new content |

After the fix, re-run Step E. **Do not power through; stop after 3
unsuccessful retries and ask the user.**

### Halted at `validate` — Check 1–10
Schema, vocab, grammar, cadence, length, etc. The error message says which
check. Most common culprits:
- **Check 5 (length)**: total content tokens out of band. Trim a sentence
  or merge two short ones.
- **Check 7 (grammar progression)**: you used a grammar point not yet
  introduced. Check `palette.py N --include-grammar`.
- **Check 9 (reinforcement)**: a critical-debt word from the brief was
  not used. Add it.

### Halted at `mint_budget`
You minted more new words than the brief's `mint_budget.max`. Two
recovery options:
- **Trim**: replace late-story mints with palette words. The brief's
  `palette.categories` lists every available word.
- **Raise the budget**: edit the spec's `intent` to justify the mint
  count, then re-run. This is legitimate when the new words form a
  coherent neighborhood matching the story's purpose; not legitimate
  when they're accidental fallout.

### Halted at `coverage_floor`
The story introduced 0 new grammar points but the current JLPT tier
(or an earlier tier) still has uncovered catalog entries. Validator
Check 3.10 fires for the same reason. Recovery:

1. Open the brief: `python3 pipeline/author_loop.py author N --brief-only`
2. Read `grammar_introduction_debt.recommended_for_this_story` — the
   prereq-ready picks. Cross-reference with the FULL
   `uncovered_in_current_tier` list because the recommendation list
   is alphabetic, not pedagogical.
3. Pick a point whose construction fits naturally in your current
   spec. The cheapest-to-introduce N5 points are typically:
     * `N5_desu` (です) — append a copula reflection sentence like
       「<adj> <noun>です。」 (zero new vocab, fits any scene).
     * `N5_ka_question` (か) — turn one assertion into a question.
     * `N5_mashita_past` (ました) — one past-tense verb.
     * `N5_masen` (ません) / `N5_arimasen` (ありません) — a single
       negative.
     * `N5_dare_who` / `N5_doko_where` — an interrogative inserted
       into a dialogue or reflection sentence.
4. Rewrite ONE sentence (or add one) to use the picked construction.
   Re-run `would-mint` to confirm no extra mints were introduced.
5. Re-run the gauntlet.

If `earlier_uncovered` is non-empty (a prior tier has gaps), address
THOSE first — Check 3.9 will hard-block tier advancement otherwise.

### Halted at `vocab_reinforcement`

(Relaxed 2026-04-29 — see AGENTS.md note. The step now only hard-blocks
when the R1 window is about to CLOSE on a word AND that word was minted
outside the bootstrap window. If you're seeing this failure, it means
some non-bootstrap word minted ~10 stories ago has zero follow-up uses
and this story is its last chance. Previous failure mode — "story N
must use every word from story N-1" — was retired.)

Your story did not reuse a word that has `must_reinforce: true` in the
brief's `must_hit.word_reinforcement.items`. The error message names every
missing `word_id` and `lemma`. These are words intro'd in the immediately
previous story; if your draft doesn't reuse them, the post-ship test
`test_vocab_words_are_reinforced` (Rule R1) will fail. Recovery:
1. Open the brief: `python3 pipeline/author_loop.py author N --brief-only`
2. Find each missing `word_id` in `must_hit.word_reinforcement.items`.
3. Add ONE sentence that uses each missing word (or fold them into
   existing sentences). The words are already in the palette by ID —
   `would-mint` will not flag them as new.
4. Re-run the gauntlet.

### Halted at `pedagogical_sanity`
Your story did not reinforce a grammar point that has `must_reinforce:
true` in the brief's `grammar_reinforcement_debt`. The error message
names every missing `grammar_id` AND prints a sample construction from
the intro story. Recovery:
1. Open the brief: `python3 pipeline/author_loop.py author N --brief-only`
2. Find the missing grammar_id in `grammar_reinforcement_debt.items`.
3. Read its `example.surface` for a concrete construction.
4. Add ONE sentence to your spec that uses the same construction
   (substituting nouns/objects to fit your scene).
5. Re-run the gauntlet.

This step exists because the post-ship pytest suite checks the same
thing; without this step, the failure surfaces only after `--ship` and
requires a clean-up. The gauntlet pulls it forward to dry-run.

### Halted at `literary_review` (CANNOT HAPPEN — retired 2026-04-29)
The Python `step_literary_review` was removed from `author_loop.py`.
If you ever see this step name in gauntlet output, you're running an
old checkout — pull. The literary-review discipline now lives entirely
in this skill (§B.0, §B.1, §E.5, §E.6, §E.7, §G).

## 4. Best-practice patterns (from the audit + SHIP-list analysis)

The 18 v1 stories that passed the audit clean (1, 5, 10, 16, 23, 25, 26,
29, 34, 41, 42, 45, 46, 48, 49, 51, 52, 56) cluster around three
structures. Use one of these unless you have a specific reason not to:

1. **Concrete object as anchor** — a key, a letter, a leaf, a box. The
   object forces causality (it gets placed, found, given, opened).
2. **Two characters with a shared task** — bringing bread to a bird,
   meeting at a station, exchanging letters. The second character forces
   dialogue or action.
3. **A single sensory beat sustained** — one rainstorm, one walk, one
   morning. NOT seven disconnected images.

**Avoid (the audit's failure structures):**
- Seven disconnected images sharing only setting (the "missing-arc" defect).
- Pure observation with no actor change of state.
- Pseudo-poetic equivalences when concrete language was available.

## 5. Token-economy rules

To keep authoring cheap:
- **Read the brief once, fully.** Do not re-fetch it mid-loop.
- **`would-mint` every candidate before writing it to the spec**, not
  after. One `would-mint` call ≈ 3 build-iteration tool calls.
- **Never call `expand_code_chunks` on `pipeline/semantic_lint.py`** for
  authoring. The brief and §3's table contain everything you need.
- **Never run pytest as a "did it work" check** when `author_loop.py
  --dry-run` already reports the same failures faster and with sentence
  context.
- **Use `pipeline/tools/vocab.py search` and `pipeline/tools/spec.py
  show`** for surgical inspections, not `open_files` on JSON files.

## 6. Authoring tone (the literary contract)

The corpus voice is **concrete, quiet, kind**. Not poetic, not clever, not
philosophical. The narrator notices specific things and does specific
things. Other beings have agency.

**Match the era's north-star.** The brief gives you up to 3 north-stars
for the current era; one of your sentences should *feel like* one of them.
If story 10's north-star is dialogue-arrives, your story 11 should not
revert to pure observation.

**Avoid LLM "literary" tells:**
- "the X is the X of the Y" equivalences
- decorative noun-piles dressed as closers
- 静か as a default mood when nothing is actually quiet
- 思います as universal hedge
- pathetic-fallacy "X looks at me from the window" cycling
- "warm/quiet/gentle" as evaluation without earning it

**The audit's harsh rule of thumb:** if a sentence makes you (the agent)
feel "that sounded poetic," it probably failed the v2 lints. Read it
again with the anti-patterns in mind.

## 6.5. The override budget (§G — the ONE rationalization cap)

**Why this exists.** Every gate above is honest only if "no" actually
costs something. Without a hard cap, a tired or hurried author will
quietly downgrade three "no"s into "yeah but"s and ship anyway. The
override budget is the single mechanism that makes the gates bite.

**The rule:** every authoring session has **one (1) override token**.
An override is consumed when:

- §B.1 forbidden zone is violated by deliberate exception
  (`OVERRIDE: <field> violated because…` in the spec's `intent`).
- §E.5 prosecutor table has a contract row marked N and the story
  ships anyway because "the alternative is worse" (DISCOURAGED — almost
  always means restart Step B).
- §E.6 EN-only difference sentence required an escape hatch and
  the story ships anyway.
- §E.7 fresh-eyes subagent returned REWRITE-STORY and the story
  ships anyway.

**The second override in a session forces escalation:** stop, do NOT
ship, surface to the user with ≤5 lines describing what each override
was for and why proceeding looked tempting. The user decides whether
to spend the second override or to restart from a different premise.

**Track the budget visibly** in the §G report at the end of the
session: `overrides_used: <count>/<1>; details: …`. Future sessions
reading the spec's `intent` block will see the override note and know
why an apparent rule violation was tolerated. If the corpus ever
audits to "every story has an override," the rules are mis-calibrated
and need to be re-tuned, not the budget bumped.

**Override-by-budget is the only sanctioned bypass.** "Yeah but
technically Y" is NOT an override — it's the failure mode the budget
exists to prevent. If you find yourself writing "technically" in §E.5,
that IS a §E.5 = N answer.

## 7. Escalation criteria (when to stop and ask)

Stop and ask the user (do NOT keep retrying) when:
- 3 retries on the same lint have failed.
- The brief reports `critical_count > 0` AND you cannot find a sentence
  that uses the critical-debt word naturally (the corpus may need a vocab
  reorder, not a story).
- The user's intent ("write a story about X") cannot be satisfied within
  the current word/grammar budget.
- You're tempted to `would-mint`-bypass with `--allow-mint` flags.
- The literary review (when implemented) escalates 3 rounds.

In each case, surface the specific blocker in ≤5 lines and propose 1–2
options. Do not silently soldier on.

## 8. Reference docs (for cases this skill doesn't cover)

- **`docs/phase4-bootstrap-reload-2026-04-29.md`** — **THE current authoring contract.**
  Defines the v2.5 BOOTSTRAP_LADDER (per-story vocab/grammar caps for stories
  1..10), the prescriptive seed plan (`data/v2_5_seed_plan.json`), the scene
  plan, the validation gates, and the cascade procedure used to wipe v2.0.
  Read this BEFORE any story 1..10 ship; the brief's `must_hit.seed_plan`
  surfaces the relevant slot but the doc gives the full rationale.
- `data/v2_5_seed_plan.json` — per-slot prescriptive vocab + grammar + scene
  plan for stories 1..10 (read by the brief).
- `data/scene_affordances.json` — per-scene noun/character/action palette
  (read by the brief and surfaced as `must_hit.scene_affordances`).
- `docs/audit-2026-04-27.md` — the v1 literary audit; defect inventory + SHIP-list patterns
- `docs/v2-strategy-2026-04-27.md` — the v2 architecture (lints, tools, agent reframe)
- `docs/phase3-tasks-2026-04-28.md` — the Phase-3 task plan (most superseded by Phase 4)
- `AGENTS.md` (workspace root) — schema gotchas, cascade rules, shell quirks
- `pipeline/semantic_lint.py` — the rules themselves (only read if you need to know WHY a rule fired)

## 9. Quick reference: the canonical commands

```bash
# Activate venv FIRST in any bash invocation that touches fugashi/jamdict
source .venv/bin/activate

# Get the brief (Step A) — surfaces ladder + seed_plan + scene_affordances
# for stories 1..10 (BOOTSTRAP_LADDER); falls through to steady-state for 11+.
python3 pipeline/author_loop.py author N --brief-only

# Pretty-printed brief
python3 pipeline/tools/agent_brief.py N --pretty

# Inspect the ladder + seed plan for a slot directly (no brief overhead)
python3 -c "import sys; sys.path.insert(0,'pipeline'); from grammar_progression import ladder_for; print(ladder_for(N))"
python3 -c "import json; print(json.dumps(json.load(open('data/v2_5_seed_plan.json'))['stories'].get(str(N), {}), ensure_ascii=False, indent=2))"

# Just the palette in human format
python3 pipeline/tools/palette.py N --format human --include-grammar

# Compute the mechanical forbidden zones (Step B.1 — paste SUMMARY into spec)
python3 pipeline/tools/forbid.py N

# Check a candidate sentence (Step C — every sentence)
python3 pipeline/tools/vocab.py would-mint "候補の日本語"

# Run the gauntlet, dry-run (Step E)
python3 pipeline/author_loop.py author N --dry-run

# Run the gauntlet, ship (Step F — runs state_updater,
# regenerate_all_stories, and audio_builder automatically as part of
# the live ship; no manual chain needed.)
python3 pipeline/author_loop.py author N

# Manual recovery: re-run individual post-ship steps if a ship was
# interrupted (rarely needed; the gauntlet runs all of these on a
# successful live ship).
python3 pipeline/regenerate_all_stories.py --story N --apply
python3 pipeline/state_updater.py stories/story_N.json
python3 pipeline/audio_builder.py --vocab data/vocab_state.json stories/story_N.json

# Backfill grammar intro_in_story across the whole corpus (idempotent;
# only needed once after a fresh clone of an old corpus).
python3 pipeline/tools/backfill_grammar_intros.py

# Catalog coverage report (per-tier covered/remaining)
python3 pipeline/grammar_progression.py

# Backfill audio for older stories (cheap, incremental)
for n in $(seq 1 N); do
  python3 pipeline/audio_builder.py --vocab data/vocab_state.json stories/story_$n.json
done

# Full test sweep (Step F — also use after manual edits)
python3 -m pytest pipeline/tests/ -q

# Inspect a single shipped story
python3 pipeline/tools/story.py show N

# Commit proposal (Step F.3 — propose, then ASK before running)
git add stories/story_N.json pipeline/inputs/story_N.bilingual.json \
        data/vocab_state.json data/grammar_state.json audio/story_N/
git status
# then ASK the user before: git commit -m "..." && git push
```

---

*The goal of this skill: the user types `author story 11` and a clean
story ships. Everything in this file exists to make that two-word prompt
sufficient. If you find yourself asking the user for clarification on
rules that are documented above, you've failed the skill's purpose —
re-read §0–§3 and try again.*
