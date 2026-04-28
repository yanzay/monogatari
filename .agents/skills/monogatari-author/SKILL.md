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
- `grammar_reinforcement_debt` — **READ THIS FIRST.** Lists every grammar
  point intro'd in the last W stories that still needs reinforcement.
  Items with `must_reinforce: true` MUST appear in this story; the
  gauntlet's `pedagogical_sanity` step blocks if you skip them. Each
  item ships with an `example.surface` showing a concrete construction
  you can adapt.
- `north_stars` — the era's 1–3 voice templates (this is the tone you must match)
- `previous_3_stories` — what the prior corpus just did (avoid repeating motifs)
- `previous_closers` — the literal closer of the last 3 stories. Do NOT
  echo their structure; vary openings AND endings.
- `reinforcement_debt` — words you MUST use soon
- `lint_rules_active` — the 10 rules your spec must pass
- `anti_patterns_to_avoid` — the 5 audit defects with bad/fix examples

**Internalize the north_stars, anti_patterns, AND `must_reinforce`
items before drafting a single sentence.** Do not skim them.

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

This runs: spec_exists → agent_brief → build → validate (incl. all 10 lints)
→ literary_review (stub) → would-write → audio (stub).

**Read the output carefully.** If `VERDICT: would_ship`, proceed to Step F.
If `VERDICT: fail`, see §3 (failure recovery).

### Step F — Ship (only if Step E was clean)

```bash
source .venv/bin/activate && python3 pipeline/author_loop.py author N
```

(Same command without `--dry-run`.) Then run the regenerator to set the
`is_new` flags correctly:

```bash
source .venv/bin/activate && python3 pipeline/regenerate_all_stories.py --story N --apply
```

Then verify the full test suite (NOT just the per-story slice — the
post-ship state may break other stories' reinforcement windows):

```bash
source .venv/bin/activate && python3 -m pytest pipeline/tests/ -q
```

#### Step F.1 — Generate audio (REQUIRED for new stories)

For any newly-shipped story (or any story where the sentence count or
text changed), generate audio. This is part of shipping, not a separate
manual step:

```bash
source .venv/bin/activate && python3 pipeline/audio_builder.py \
    --vocab data/vocab_state.json stories/story_N.json
```

The builder is incremental — it skips files that already exist with the
matching content hash, so it's cheap to re-run. Use `--force` only when
you've changed an existing sentence and need to overwrite. The builder
writes to `audio/story_N/`. **Do NOT skip this step** — incomplete audio
ships a broken reading experience to the user.

If the audio builder fails (network, GCP credentials, quota), STOP and
report the failure to the user; do NOT proceed to commit. Audio is part
of the shipping contract.

#### Step F.2 — Self-review BEFORE proposing the commit

Before committing, run the §C.4 self-audit ONE MORE TIME on the actual
shipped artifact. Open `stories/story_N.json` and re-read the sentences
in order. Ask:

- Does it tell a story? (Not "did it pass tests" — does it READ as a story?)
- Would I ship this if a human reviewer were going to read it next?
- Does the closer earn its slot, or is it filler?

If the answer to any is "no," DO NOT commit. Report the literary defect
to the user and propose a re-author. Test-passing is necessary but not
sufficient — the literary contract is yours to honor (cf. §C.3).

#### Step F.3 — Propose the commit (only if F.2 passed)

When the self-review passes, propose a git commit to the user. Include:
- A 1-line summary: `Add story N: <title_jp> / <title_en>`
- A 3–5 line body describing the structural choice and any new mints/
  reinforcements landed.
- The exact files staged: `stories/story_N.json`,
  `pipeline/inputs/story_N.bilingual.json`, `data/vocab_state.json`,
  `data/grammar_state.json`, `audio/story_N/`, and any
  `state_backups/regenerate_all_stories/` snapshot.

ALWAYS confirm with the user before running `git commit` and
`git push` — those are write operations the user did not explicitly
request unless they typed "ship and push" / "commit" / "push" in
their original prompt. Default behavior: run `git status` and
`git diff --stat`, then ASK.

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

# Run the gauntlet, ship (Step F)
python3 pipeline/author_loop.py author N

# Recompute is_new flags (Step F, after shipping)
python3 pipeline/regenerate_all_stories.py --story N --apply

# Generate audio for a shipped story (Step F.1, REQUIRED for new stories)
python3 pipeline/audio_builder.py --vocab data/vocab_state.json stories/story_N.json

# Full test sweep (Step F)
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
