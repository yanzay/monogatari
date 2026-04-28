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

#### Step B.1 — Narrative coherence checklist (THE LITERARY CONTRACT)

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

### Step E — Run the full gauntlet (1 tool call)

```bash
source .venv/bin/activate && python3 pipeline/author_loop.py author N --dry-run
```

This runs: spec_exists → agent_brief → build → validate (incl. all 10
lints AND Checks 3.6/3.9/3.10 grammar coverage) → mint_budget →
pedagogical_sanity (grammar reinforcement) → vocab_reinforcement (R1
must-reinforce words) → coverage_floor (grammar introduction)
→ literary_review (stub) → would-write → audio (skipped on dry-run;
real on live ship).

**Read the output carefully.** If `VERDICT: would_ship`, proceed to Step F.
If `VERDICT: fail`, see §3 (failure recovery).

### Step F — Ship (only if Step E was clean)

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

#### Step F.2 — Critical literary review (DISCARD-AND-REWRITE gate)

**This is a hard quality gate, not a formality.** Tests passing means
the story is technically valid — not that it is good. Bad stories are
permanent corpus pollution; the cost of one extra rewrite iteration is
trivial next to shipping a defect that future stories will be measured
against.

Re-open `stories/story_N.json` and read the sentences in order, **as
if you were a human learner picking the corpus up for the first time**
(no knowledge of mints, debt, lints, or tier policy — just the story).
Then answer ALL of these. **Each "no" is a discard signal.**

**The five-question gate:**

1. **What HAPPENS in this story?** State it in one sentence with a
   verb of action, transfer, or discovery. If you can only say "the
   narrator notices X" or "X exists, then Y exists" — that is
   observational filler. **Discard.**
2. **Does the closer surprise, settle, or land?** A great closer either
   resolves a tension (object found, action completed, character
   responds) or leaves a deliberate sensory beat. A closer that simply
   restates the setting in different words, or that mirrors the closer
   of the last 3 stories, is filler. **Discard.**
3. **Does the anchor object DO something?** It must change owners,
   change state (open/close/break/cook/write/tear), change location
   meaningfully, OR trigger an action. If it only gets *looked at* and
   *held*, it is decoration. **Discard.**
4. **Is each sentence load-bearing?** Cover each sentence with your
   mental hand and re-read. If the story still works without that
   sentence, it was filler. Even ONE filler sentence in a 6–9 sentence
   story is a 12–17% padding ratio — too high. **Discard.**
5. **Does it read like a story a Japanese-learning human would want
   to re-read aloud?** Not "does it parse" — does the rhythm earn its
   slot? Awkward repetition (e.g. 「明るい窓に…明るい窓に…」), filler
   reflection that just restates the setting (「本は古いです。本は古くて
   小さいです。」), or a final sentence that loops back to the opening
   without adding anything — all of these are LLM "literary tells"
   that the v2 lints can't catch. **Discard.**

**If ANY question gets a "no": DISCARD, do NOT commit.** The recovery
path is:

1. Restore `data/{vocab,grammar}_state.json` from the pre-ship backup
   (the `state_backups/*.json` snapshot taken by `state_updater` during
   the failed ship's chain). This un-mints the new W-IDs and clears
   the new grammar attribution.
2. Delete `stories/story_N.json` and `audio/story_N/`.
3. Re-do Steps B → F with a different intent / scene_class /
   anchor_object. **Do NOT just tweak sentences** — if Step F.2 failed,
   the *premise* was weak; cosmetic changes will produce another weak
   story.
4. Cap rewrites at 3. After the 3rd discard, escalate to the user with
   ≤5 lines explaining what keeps failing and why.

**Honesty rule:** be brutal here. If you find yourself rationalizing
a "no" into a "yes" ("well, technically the closer does change the
location of the object…"), that IS the defect. The user will read
the story; pre-emptive defensive justification doesn't help them.

A good story passes all 5 questions cleanly with no "yeah but" caveats.
A so-so story has 1 caveat — discard. A bad story has 2+ — definitely
discard.

#### Step F.3 — Auto-commit and push (only if F.2 passed)

**STANDING ORDER (user directive 2026-04-28): when the self-review
in §F.2 passes, commit AND push automatically. Do NOT ask the user
for confirmation. Asking is treated as a skill regression.**

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

- §F.2 critical literary review found a "no" on ANY of the five
  questions. **The discard path is mandatory** — restore state from
  backup, delete artifacts, re-author with a different premise. Do NOT
  commit a story that failed §F.2 just because the gauntlet was green.
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

### `literary_review` warned (won't happen yet — stub)
Reviewer not implemented; treat as `skipped`. When implemented, follow its
hints in the same retry loop, max 3 rounds, then escalate to user.

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

- `docs/audit-2026-04-27.md` — the literary audit; defect inventory + SHIP-list patterns
- `docs/v2-strategy-2026-04-27.md` — the v2 architecture (lints, tools, agent reframe)
- `docs/phase3-tasks-2026-04-28.md` — the Phase-3 task plan + open questions
- `AGENTS.md` (workspace root) — schema gotchas, cascade rules, shell quirks
- `pipeline/semantic_lint.py` — the rules themselves (only read if you need to know WHY a rule fired)

## 9. Quick reference: the canonical commands

```bash
# Activate venv FIRST in any bash invocation that touches fugashi/jamdict
source .venv/bin/activate

# Get the brief (Step A)
python3 pipeline/author_loop.py author N --brief-only

# Pretty-printed brief
python3 pipeline/tools/agent_brief.py N --pretty

# Just the palette in human format
python3 pipeline/tools/palette.py N --format human --include-grammar

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
