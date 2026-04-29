---
name: monogatari-author
description: >
  Author a Monogatari graded-reader Japanese short story end-to-end. Use when the user
  says "author story N", "write the next story", "draft story X", "monogatari author",
  or any variant of "make a new story for the corpus". Runs the full v2 gauntlet
  (palette → spec → build → lints → validate → ship) and recovers from each failure
  category without further prompting. Aim: user types two words, agent ships a story.
---

# Monogatari Author Skill

You author v2 Monogatari graded-reader stories. The user types `author story N`; you ship.

## 0. Activation

Triggers: "author story N", "author next story", "write story N", "draft story N", "new story", "monogatari author", "make a story". Bare `author` ⇒ N = max(existing)+1.

### 0.0 The full ordered procedure (do not skip, do not reorder)

1. **§A** — get the brief.
2. **§A.5** — internalize seed plan (stories 1–10 only).
3. **§B** — choose intent + scene_class + anchor.
4. **§B.0** — write PREMISE CONTRACT into spec `intent`. **REQUIRED.**
5. **§B.1** — run `forbid.py N`; paste SUMMARY into spec; satisfy all 4 zones. **REQUIRED.**
6. **§B.2 / §C / §C.1–§C.4** — narrative checklist, mint budget, draft, self-audit.
7. **§D** — write the bilingual spec.
8. **§E** — gauntlet dry-run; iterate to `would_ship`.
9. **§E.5** — write `.author-scratch/prosecution_N.md`. **REQUIRED.**
10. **§E.6** — EN-only re-read of stories N, N-1, N-2. **REQUIRED.**
11. **§E.7** — fresh-eyes literary subagent. **REQUIRED.**
12. **§E.7.5** — native-naturalness subagent. **REQUIRED.**
13. **§E.8** — round-trip cap (max 3); escalate on 4th.
14. **§F** — live ship. Pytest sweep.
15. **§F.3** — auto-commit and push.
16. **§F.4** — verify spec/artifact drift; fast-follow if needed.
17. **§G** — final report; record `overrides_used: <count>/1`.

Skipping any of §B.0, §B.1, §E.5–§E.7.5 is a discipline violation. Backfill the missing artifact post-hoc and log the lapse in `.author-scratch/prosecution_N.md`.

### 0.1 Authoring contract for stories 1–10

`docs/phase4-bootstrap-reload-2026-04-29.md` is the source of truth. The brief surfaces `hard_limits.ladder`, `must_hit.seed_plan`, `must_hit.scene_affordances`. For stories 11+, steady state applies (1 grammar / 3–5 vocab; no scene constraint).

## 1. Hard invariants

1. **NEVER edit `stories/story_N.json` directly.** Only edit `pipeline/inputs/story_N.bilingual.json`.
2. **NEVER bypass `pipeline/author_loop.py`.** Use `--dry-run` to test.
3. **Vocabulary is derived, not declared.** Set a mint budget; let `state_updater` mint on ship. (Story 1 is the exception — declare the seed.)
4. **NEVER add words/grammar above current tier.** Check the verb's standard construction too: `言います` is N5 but `「X」と言います` is N4 (G028).
5. **NEVER touch `data/vocab_state.json` or `data/grammar_state.json` directly.** Only `state_updater` writes them.
6. **Story 4+ MUST introduce ≥1 new grammar point** until the current tier is fully covered. The brief's `grammar_introduction_debt.must_introduce` flags this; `coverage_floor` and Check 3.10 hard-block.

## 2. The procedure

Use `update_todo` to track these steps.

### Step A — Get the brief (1 tool call)

```bash
source .venv/bin/activate && python3 pipeline/author_loop.py author N --brief-only
```

Read it fully. Key fields:
- `size_band` — sentence + content-token target.
- `mint_budget` — `{min, max, target}`. Gauntlet HARD-FAILS if `len(new_words) > max`.
- `palette.categories` — available words by sense (★ = due, ★★ = critical-debt).
- `grammar_points` — available grammar.
- `grammar_introduction_debt` — `must_introduce`, `current_jlpt`, `coverage_summary`, `recommended_for_this_story` (sorted alphabetically — scan full `uncovered_in_current_tier`), `earlier_uncovered` (address first; Check 3.9 blocks tier advancement).
- `grammar_reinforcement_debt` — items with `must_reinforce: true` MUST appear; each ships with `example.surface`.
- `must_hit.grammar_introduction.recommended[0]` — default pick (ranked by leverage). Use it unless premise demands otherwise; document deferral in `intent`. Don't pick low-leverage leaves (誰, いつ) just because they're easy.
- `must_hit.word_reinforcement` — words from prev story; items with `must_reinforce: true` MUST appear (R1 / `vocab_reinforcement` step).
- `north_stars`, `previous_3_stories`, `previous_closers`, `lint_rules_active`, `anti_patterns_to_avoid`.

Internalize `must_introduce`, `must_reinforce`, north_stars, anti_patterns BEFORE drafting.

### Step A.5 — Seed plan (stories 1–10 only)

`must_hit.seed_plan` carries: `scene_class`, `intent_seed`, `anchor_object_candidates`, `characters_min`, `vocab_seed` (prescribed lemma identity), `grammar_seed`, `rationale`. Deviations cost a §G override and must be documented in `intent`. Stories 11+: empty seed; fall through.

### Step B — Choose intent + scene + anchor (in head)

Decide three things, write them down:
1. **`intent`** (1–2 sentences): what story is this? Verb-driven, not observational.
2. **`scene_class`**: NOT used in previous 3 stories.
3. **`anchor_object`**: appears in ≥3 sentences with a verb (placed/opened/carried/given), not as decoration.

If you cannot answer crisply, restart.

#### Step B.0 — Premise contract (REQUIRED)

Paste into spec `intent`, in English, six fields filled:

```
PREMISE CONTRACT (story N)
  one_sentence_event:    <subject> <action verb> <object> because <reason>.
  change_of_state:       at s0 X; at closer Y; X≠Y.
  scene_novelty_claim:   "I am NOT writing a {prev scene_class} story" (or honest exception).
  anchor_novelty_claim:  "Anchor is <X>. Last appeared in story <N or never>."
  closer_shape_claim:    "Closer shape: <action|dialogue|sensory>. NOT a noun-pile, NOT
                         a 「Nは Adj です」 mirror of stories <prev_3>."
  why_not_filler:        per character/object, why does each EARN its slot?
  obligations_absorbed:  must-reinforce <wid…>, must-introduce <gid>; how absorbed
                         (NOT bolted on at s4).
```

If a field cannot be filled crisply, restart §B. Do not soften after drafting — §E.5 judges against this exact text.

#### Step B.1 — Forbidden zones (REQUIRED)

```bash
source .venv/bin/activate && python3 pipeline/tools/forbid.py N
```

Paste SUMMARY block into spec `intent` under `FORBIDDEN THIS STORY:`. Satisfy all four zones (scene_class last 3, anchor last 5, opening tokens last 3, closer shapes last 3). Violation requires a §G override documented as `OVERRIDE: <field> violated because…`.

#### Step B.2 — Narrative coherence checklist

All five must answer YES before drafting:

1. **What changes between s0 and closer?** "Nothing" = observational filler — restart.
2. **Where does each character enter?** Mid-story appearances need an entrance sentence (door, footsteps, voice). Solitary scenes are fine.
3. **What does the anchor DO?** Must satisfy ≥1 of: change owners, change state, change location meaningfully, trigger character action. "Held then still held" = decoration.
4. **Does every character have a purpose?** A second character must force dialogue, action, or transfer. No grammar-bait friends.
5. **"What happens?"** must answer with an action/transfer/change verb. "I observe" = no arc — restart.

### Step C — Mint budget + draft

**Budget = (count, neighborhood).** Defaults: story 1 = 10–16, stories 2–5 = 2–5, 6–15 = 1–4, 16+ = 0–3. Neighborhood matches story intent.

For each candidate sentence:

```bash
source .venv/bin/activate && python3 pipeline/tools/vocab.py would-mint "<候補の日本語>"
```

Use as a count check, not a gate. Over budget → trim mints OR raise budget in `intent` (gauntlet `mint_budget` step hard-fails over `mint_budget.max`).

For each new mint, also check: does the verb's standard construction (te-form, ています, と quotative) require above-tier grammar? If yes, defer.

#### Step C.1 — Reflection slot

A `reflection` role MUST add new information. Restating an established attribute (setting: 「小さい卵」, reflection: 「卵は小さいです」) is filler. Cover-with-hand test: if nothing is lost, cut or rewrite.

#### Step C.2 — Closer cliché ladder

Closer must NOT structurally mirror previous_closers (same template, swapped noun = mirroring). Currently banned for stories 4–8: `[X]は[Y]を[Z]に持ちます`, `[X]は[Y]を見ます` (unless real change of state), `[X]は「Z」と言います` (limit 1 per 3). Fresh patterns: dialogue line, departure (`友達は道を歩きます`), settling (`卵は机の上にあります`), relational beat (gaze flips), sensory closer.

#### Step C.3 — Pedagogical-vs-narrative tension

When `must_reinforce: true`: (a) native fit (best), (b) rebuild scene (expensive), or (c) defer to N+1 (document in `intent`). FORBIDDEN: jamming the must-reinforce surface into a contradicting sentence (teleporting friend into solitary scene). If (b) gets ugly, choose (c).

#### Step C.4 — Self-audit

Before §E:
1. One-sentence summary uses an action/transfer/change verb? Else restart.
2. s0 vs closer: anything changed (location, possession, character on stage, time, narrator's understanding)? Else restart.
3. Cover each sentence — is anything lost? Else cut.
4. Closer matches no item in §C.2 ladder? Else rewrite.

Per-sentence:
- Declare `role`: `setting | action | dialogue | inflection | reflection | closer`. Story must contain ≥1 of {action, dialogue, inflection}.
- Closer must have a verb other than the final copula (lint 11.7).
- Avoid the 5 anti-patterns: tautological-equivalence (`XのYはZのYです`), closer-noun-pile, bare-known-fact (`〜と思います` on asserted fact), misapplied-quiet (`静か` on inanimate objects), decorative-noun.

### Step D — Write the bilingual spec

Write `pipeline/inputs/story_N.bilingual.json`:

```json
{
  "story_id": N,
  "title": {"jp": "...", "en": "..."},
  "intent": "<§B + §B.0 contract + §B.1 FORBIDDEN block>",
  "scene_class": "...",
  "anchor_object": "...",
  "characters": ["narrator", "..."],
  "sentences": [
    {"jp": "...", "en": "...", "role": "setting"},
    ...
    {"jp": "...", "en": "...", "role": "closer"}
  ]
}
```

If the spec already exists, back it up:

```bash
cp pipeline/inputs/story_N.bilingual.json /tmp/story_N.bilingual.json.bak
```

### Step E — Gauntlet dry-run; iterate to green FIRST

```bash
source .venv/bin/activate && python3 pipeline/author_loop.py author N --dry-run
```

Steps run: spec_exists → agent_brief → build → validate (Checks 1–11 incl. 3.6/3.9/3.10) → mint_budget → pedagogical_sanity → vocab_reinforcement → coverage_floor → would-write → audio (skipped on dry-run).

If dry-run fails, see §3 and re-run until `VERDICT: would_ship`. **Run literary review (§E.5–E.7.5) ONLY against gauntlet-green text.** Sentence rewrites forced by the gauntlet invalidate any prior literary verdict.

> ⛔ **STOP — `would_ship` is correctness, not literary, not natural. Next is §E.5, NOT §F.**

**Freshness rule (applies to §E.5/E.6/E.7/E.7.5).** Each runs ONLY after §E is green AND prior literary gates returned SHIP. Any sentence-level edit (see §E.8 trivial-edit carryover) invalidates the prior verdict — re-run.

### Step E.5 — Prosecutor pass

Re-read the spec as a hostile critic. Write `.author-scratch/prosecution_N.md` (NOT `/tmp/`). Required structure:

```markdown
# PROSECUTION — story N

| sentence | role | could I delete it and lose nothing? | concrete-physical verb? | object load-bearing? |
|---|---|---|---|---|
| s0 | setting | Y/N + reason | — | — |
| ... |
| closer | closer | matches §B.0 closer_shape_claim? Y/N | mirrors prev 3? Y/N | — |

## Contract checks (against §B.0)

| field | honored? | concrete evidence (sid + surface) |
|---|---|---|
| one_sentence_event   | Y/N | … |
| change_of_state      | Y/N | s0=…, closer=…, X≠Y? |
| scene_novelty_claim  | Y/N | … |
| anchor_novelty_claim | Y/N | … |
| closer_shape_claim   | Y/N | … |
| why_not_filler       | Y/N | … |
| obligations_absorbed | Y/N | … |
```

Re-open and READ it. "Yeah but / technically Y" = **N**.

**Decision:** ANY contract row = N → **discard, restart §B**. Per-sentence row = N → fix the sentence, BOUNCE BACK to §E, re-run §E.5 on new text.

`.author-scratch/` is convention-gitignored — do not commit prosecution files.

### Step E.6 — EN-only re-read

Open `pipeline/inputs/story_{N,N-1,N-2}.bilingual.json`. Read `en` fields ONLY. Write one sentence: "What is materially different about the EVENTS of story N vs N-1 and N-2?"

Discard signals (escape hatches): "anchor is different object", "scene_class is different", "grammar point is different", "mood/tone is different".

Acceptable verbs: discovers, transfers, refuses, chooses, fails, surprises, breaks, finishes, decides, declines, reveals.

If you cannot write the sentence without an escape hatch → discard.

### Step E.7 — Fresh-eyes literary subagent (1 tool call)

Delegate to an `Explore` subagent with this **exact** prompt (hostility is load-bearing):

> "You are a HOSTILE LITERARY REVIEWER for a Japanese graded-reader corpus. Find reasons to REJECT. Default verdict is REWRITE; SHIP must be earned. Do not be polite.
>
> READ ONLY: `pipeline/inputs/story_N.bilingual.json`, `pipeline/inputs/story_{N-1,N-2,N-3}.bilingual.json`. NOT AGENTS.md, the SKILL, the brief, the corpus.
>
> Read EN glosses first, then JP. In ≤250 words, answer ALL eight probes (be specific — quote sids; vague = N):
>
> 1. ONE-SENTENCE EVENT: write the story in one sentence using a verb of action/transfer/decision/refusal/discovery/revelation (NOT observes/is/notices). Observational only = REWRITE-STORY.
> 2. CHARACTER ENTRANCES: name the entrance sentence for every non-narrator. Mid-story appearance with no entrance = TELEPORT = REWRITE-STORY.
> 3. WHY-IS-EACH-FACT-HERE: for each assertion (esp. negative), why would the story suffer if deleted? "To satisfy a grammar slot" = PEDAGOGICAL BOLT-ON. 2+ bolt-ons = REWRITE-STORY.
> 4. ANCHOR CAUSALITY: anchor sentences. Does it (a) change owners, (b) change state, (c) change location meaningfully, (d) trigger character action? Else decoration = REWRITE-STORY.
> 5. CLOSER WEIGHT: does it land? Mechanical "and then X" = REWRITE-SENTENCE.
> 6. SAMENESS PROBE: vs N-1, N-2, N-3, repetition of anchor TYPE / event SHAPE / sentence RHYTHM / closer TEMPLATE? 3+ sames = REWRITE-STORY.
> 7. LEARNER TEST: JLPT N5 learner week 4 — (a) read a story, (b) did a grammar exercise, (c) confused? Only (a) is SHIP.
> 8. WOULD-I-WRITE-THIS: would you accept this draft from a paid author? Send-back = REWRITE.
>
> VERDICT (default REWRITE):
>   - SHIP — only if all 8 probes positive AND it's a story, not a worksheet.
>   - REWRITE-SENTENCE — name sids + defects in one line each. Story sound, 1–2 surgical edits.
>   - REWRITE-STORY — premise is the problem.
>
> 'Mostly fine' / 'good enough' / 'technically valid' = REWRITE wearing a polite mask. Strip it."

Verdict handling:
- SHIP → §E.7.5.
- REWRITE-SENTENCE → fix, BOUNCE to §E, re-run §E.5/E.6/E.7.
- REWRITE-STORY → discard, restart §B. Override only by spending §G token AND documenting concrete error in subagent's reasoning sentence-by-sentence.

**Calibration:** if last 5 §E.7 verdicts were all SHIP, paraphrase the prompt to demand ARGUE-FOR-REWRITE first.

### Step E.7.5 — Native-naturalness subagent (1 tool call)

Delegate to a fresh `Explore` subagent:

> "You are a HOSTILE NATIVE JAPANESE READER (L1, professional editor of learner materials). Find every sentence a native speaker would NOT write. Default verdict is REWRITE.
>
> READ ONLY: `pipeline/inputs/story_N.bilingual.json`. NOT AGENTS.md, the SKILL, the brief, the corpus, other stories.
>
> Audience: JLPT N5 learner, week 4. JP must be SIMPLE AND NATURAL. Pedagogical awkwardness ('お金で買う', '台所へ歩く') is the gate's target. A graded reader is not a particle drill.
>
> For EACH sentence, produce a row:
>
> | sid | jp surface | natural? Y/N | if N, natural rewrite | failure tag |
>
> Failure tags (multiple OK):
>   - WRONG-VERB (持つ for 取る/受け取る/出す; 見る on people without action; 歩く when 行く meant)
>   - WRONG-PARTICLE (で with stative-持っています; を on non-direct-object; に vs へ misuse)
>   - REDUNDANT-PEDAGOGY (お金で買う; particles correct but semantically empty)
>   - SIZE-ON-MASS (小さい/大きい on uncountable liquid/food without container)
>   - WRONG-FORM (持ちません where 持っていません meant; 〜ます where 〜ました needed; bare 〜てください with no addressee)
>   - DANGLING-QUOTE (「…」 with no 言う/呼ぶ/聞く/答える)
>   - UNNATURAL-CONTENT (grammatical but implausible event)
>   - STIFF (textbook prose; 私は私の母を見ます when 母を見ます natural)
>
> Any tag → N. 'Mostly natural' / 'understandable' = N.
>
> After table:
> A. NATURALNESS SCORE: Y / total. Less than total/total = REWRITE.
> B. ROOT-CAUSE NOTES: if 2+ rows share a tag, name the root cause.
> C. VERDICT (default REWRITE):
>   - SHIP — score = total/total AND every sentence survives a JP editor's red pen.
>   - REWRITE-SENTENCE — list sids + suggested rewrites.
>   - REWRITE-STORY — vocab/grammar choices forced unnatural constructions throughout. Recommend different verb set or premise.
>
> 'Mostly natural' / 'a learner would understand' = REWRITE wearing a polite mask. Strip it."

Verdict handling:
- SHIP → §F.
- REWRITE-SENTENCE → fix, BOUNCE to §E, re-run §E.5/E.6/E.7/E.7.5. (Often single-particle/single-verb swaps — see §E.8 trivial-edit carryover.)
- REWRITE-STORY → either (a) pick a different premise the palette can express naturally (preferred for bootstrap; consult `data/v2_5_seed_plan.json`), or (b) spend §G override to add 1–2 above-tier verbs (e.g. 受け取る). **Do NOT ship anyway** — overriding native-fluency rejection ships broken Japanese.

**Calibration:** if last 5 §E.7.5 verdicts were all SHIP without any REWRITE-SENTENCE, paraphrase to demand ARGUE-FOR-REWRITE first.

### Step E.8 — Round-trip cap

Max **3 round-trips** through §E ↔ §E.5/E.6/E.7/E.7.5 per story. Round-trip = "gauntlet green → literary or naturalness review forced an edit → gauntlet re-run." After 3rd, escalate to user in ≤5 lines: what each round-trip changed, current blocker, one proposed simplification.

**Trivial-edit carryover.** Punctuation fixes, single-particle swaps within one sentence, whitespace fixes do NOT invalidate prior verdicts and do NOT consume a round-trip slot. Threshold: if `git diff` shows changes to a `jp` field that altered surface lemmas or predicate, it's a real edit.

**Round-trip 4+:** do NOT ship even if eventually green. Defer or re-tune the seed plan / ladder.

### Step F — Live ship

> ⛔ **GATE.** Confirm before live ship:
> - `.author-scratch/prosecution_N.md` exists; all contract rows = Y. (§E.5)
> - §E.6 EN-only difference sentence written; no escape-hatch phrase.
> - §E.7 returned SHIP.
> - §E.7.5 returned SHIP with NATURALNESS SCORE = total/total.
>
> Any false → do NOT live ship.

```bash
source .venv/bin/activate && python3 pipeline/author_loop.py author N
```

The live ship runs the full chain automatically: build → all gauntlet checks → write `stories/story_N.json` → `state_updater` (mints W-IDs from build report; no hand-written plan) → `regenerate_all_stories --story N --apply` → `audio_builder`. On failure: `halted_at: <step>`, non-zero exit; `state_backups/` retains prior state.

Verify:

```bash
source .venv/bin/activate && python3 -m pytest pipeline/tests/ -q
```

#### Step F.1 — Audio (auto)

`audio_builder` runs as part of §F. Per-sentence audio: `audio/story_N/s<idx>.mp3`. Per-word audio: flat `audio/words/<wid>.mp3`. Incremental; re-running is cheap. Backfill old stories:

```bash
for n in $(seq 1 N); do
  source .venv/bin/activate && python3 pipeline/audio_builder.py --vocab data/vocab_state.json stories/story_$n.json
done
```

If audio fails (network/GCP/quota), STOP and report; do NOT commit.

#### Step F.2 — RETIRED. Use §E.5–§E.7.5 instead.

#### Step F.3 — Auto-commit and push (STANDING ORDER, do not ask)

When §E.5/E.6/E.7/E.7.5 passed and gauntlet is green, commit AND push automatically. **Never ask the user.** Asking is a regression.

Procedure:
1. `git status` + `git diff --stat` (sanity check).
2. `git add stories/story_N.json pipeline/inputs/story_N.bilingual.json data/vocab_state.json data/grammar_state.json audio/story_N/ audio/words/W*.mp3 state_backups/*.json` (only the relevant files).
3. Commit:
   ```
   Add story N: <title_jp> / <title_en>

   <3–5 line body: structural choice, new mints, reinforcements landed, deferrals.>
   ```
4. `git push`.
5. Report SHA + remote URL in §G.

**Block auto-commit only when:** any literary gate had unresolved REWRITE; `git status` shows unexpected files (stage only story files; flag strays separately); on a non-`main` branch the user did not request; pre-existing unpushed commits unrelated to this story. User may say "ship but don't push" / "commit only" — otherwise: push.

#### Step F.4 — Spec/artifact drift check

After §F.3, re-read `intent` against final `sentences[]`. Verify:
1. Closer surface in `intent` 「…」 matches actual closer.
2. Grammar intro claim matches `stories/story_N.json::new_grammar`.
3. Mint count + identity matches `new_words`.
4. Reinforcement claims (W in sentence S) hold.
5. Cascade claims (e.g. "addressed in story N+1") match story N+1's spec.

If drift: rewrite `intent` to describe what shipped. If plan changed for a documented reason, add `HISTORICAL NOTE:` rather than overwriting silently. Commit as fast-follow `Reconcile story N intent prose with shipped artifact`. If no drift: log "intent verified matches artifact" in §G.

### Step G — Report (no tool call)

≤15 lines: ship status, JP/EN title, structural choice + why, audio status, commit SHA + remote URL, `overrides_used: <count>/1`. Do NOT repeat the sentence list.

## 3. Failure recovery

When `author_loop.py` reports `VERDICT: fail`, identify `halted_at` and apply:

### `spec_exists`
Spec missing or malformed JSON → re-do §D.

### `build` — "unresolved tokens"
Typo or unknown kanji form. Run `vocab.py would-mint` on the offending sentence; replace with a known word.

### `build` — "new word mints over budget"
Trim mints (replace with palette words) OR raise budget in `intent`.

### `validate` — Check 3.5 cross-tier intro
Verb's natural construction requires above-tier grammar (e.g. quotative-と in story 1). Replace construction (`いいです` instead of `「いい」と言います`) or defer the verb.

### Dry-run passed but live ship FAILED
Pre-ship vs post-ship state divergence (Check 3.5, mint_budget). State auto-resets; `git status stories/ data/` to see writes; revert if needed.

### `validate` — Check 11 (semantic_lint)

| Rule | Wrote | Write instead |
|---|---|---|
| 11.1 / 11.10 inanimate-quiet | 「本は静かです」 | Drop 静か; concrete attribute (古い, 大きい, 赤い) |
| 11.2 consumption-target | nonsense object pairing | Verb's natural object |
| 11.3 / 11.9 self-known-fact | 「夏は暑いと思います」 in summer | Plain assertion, OR hedge another being |
| 11.4 companion-to | inanimate と | Animate と-noun only |
| 11.5 redundant-mo | も decorating | Remove or add prior set |
| 11.6 location-wo | を on noun-list of locations | One を, others で/に |
| 11.7 closer-noun-pile | nouns + です no verb | Verb-bearing closer |
| 11.8 tautological-equivalence | 「猫の色は雨の色です」 | Concrete adjective or comparison with new content |

Stop after 3 unsuccessful retries on the same lint; ask the user.

### `validate` — Checks 1–10
- Check 5 (length): trim/merge sentences.
- Check 7 (grammar progression): `palette.py N --include-grammar`.
- Check 9 (reinforcement): add the critical-debt word.

### `mint_budget`
Trim or raise budget in `intent` (legitimate when new words form a coherent neighborhood).

### `coverage_floor` / Check 3.10
Story introduced 0 new grammar but tier still has uncovered points. Pick from `grammar_introduction_debt.recommended_for_this_story`; cross-check the full `uncovered_in_current_tier` (alphabetic sort masks priority). Cheap N5 picks: `N5_desu`, `N5_ka_question`, `N5_mashita_past`, `N5_masen`/`N5_arimasen`, `N5_dare_who`/`N5_doko_where`. Rewrite/add ONE sentence; `would-mint` to confirm no extra mints; re-run gauntlet. If `earlier_uncovered` is non-empty, address those FIRST (Check 3.9 blocks tier advancement).

### `vocab_reinforcement`
Some non-bootstrap word minted ~10 stories ago has zero follow-up uses and this story is its last R1 chance. Add ONE sentence using each named word_id (already in palette; not a new mint).

### `pedagogical_sanity`
Missing `must_reinforce: true` grammar from `grammar_reinforcement_debt`. Read its `example.surface`, add ONE sentence using the same construction.

### `literary_review` — CANNOT HAPPEN (retired). Pull latest if you see this.

## 4. Best-practice patterns

The 18 audit-clean v1 stories cluster around three structures — use one unless you have a reason:

1. **Concrete object as anchor** (key, letter, leaf, box). Object forces causality (placed/found/given/opened).
2. **Two characters with a shared task** (bringing bread to a bird, exchanging letters). Forces dialogue or action.
3. **A single sensory beat sustained** (one rainstorm, one walk).

**Avoid:** seven disconnected images sharing only setting; pure observation with no actor change of state; pseudo-poetic equivalences.

## 5. Token economy

- Read the brief once, fully. Don't re-fetch mid-loop.
- `would-mint` BEFORE writing each sentence (not after).
- Never `expand_code_chunks` on `pipeline/semantic_lint.py` for authoring.
- Never run pytest as a "did it work" check when `--dry-run` reports the same faster.
- Use `pipeline/tools/vocab.py search` and `pipeline/tools/spec.py show`, not `open_files` on JSON.

## 6. Authoring tone

Voice is **concrete, quiet, kind**. Not poetic, not clever, not philosophical. Narrator notices specific things; other beings have agency.

Match the era's `north_stars` — one sentence should *feel like* one of them.

**LLM "literary" tells to avoid:** "X is the X of the Y" equivalences; decorative noun-piles dressed as closers; 静か as default mood; 思います as universal hedge; pathetic-fallacy "X looks at me from the window"; "warm/quiet/gentle" as evaluation without earning it.

Rule of thumb: if a sentence felt "poetic" to write, it probably failed v2 lints.

## 6.5 Override budget

Each session has **one (1) override token**. Consumed when:
- §B.1 forbidden zone violated by deliberate exception (`OVERRIDE: <field> violated because…`).
- §E.5 contract row = N and ship anyway (DISCOURAGED — usually means restart §B).
- §E.6 difference sentence required an escape hatch.
- §E.7 returned REWRITE-STORY.
- §E.7.5 returned REWRITE-STORY (**STRONGLY DISCOURAGED** — prefer spending the override on a §G lexical addition that unlocks the natural construction).

**Second override forces escalation.** Stop, do NOT ship; surface ≤5 lines describing each override and why proceeding looked tempting.

Track in §G report: `overrides_used: <count>/1; details: …`. "Yeah but technically Y" is NOT an override — it's the failure mode the budget exists to prevent.

## 7. Escalation

Stop and ask the user when:
- 3 retries on the same lint failed.
- `critical_count > 0` AND no sentence uses the critical-debt word naturally.
- User's intent cannot be satisfied within current word/grammar budget.
- You're tempted to bypass with `--allow-mint`.
- Literary review escalates 3 rounds.

Surface the blocker in ≤5 lines and propose 1–2 options.

## 8. Reference docs

- **`docs/phase4-bootstrap-reload-2026-04-29.md`** — current authoring contract (stories 1–10).
- `data/v2_5_seed_plan.json` — per-slot prescriptive plan.
- `data/scene_affordances.json` — per-scene noun/character/action palette.
- `docs/audit-2026-04-27.md` — v1 literary audit; defect inventory.
- `docs/v2-strategy-2026-04-27.md` — v2 architecture.
- `AGENTS.md` (workspace root) — schema gotchas, cascade rules, shell quirks.
- `pipeline/semantic_lint.py` — the rules (only if you need to know WHY a rule fired).

## 9. Canonical commands

```bash
# Activate venv FIRST for anything touching fugashi/jamdict
source .venv/bin/activate

# Step A — brief
python3 pipeline/author_loop.py author N --brief-only
python3 pipeline/tools/agent_brief.py N --pretty

# Inspect ladder + seed plan
python3 -c "import sys; sys.path.insert(0,'pipeline'); from grammar_progression import ladder_for; print(ladder_for(N))"
python3 -c "import json; print(json.dumps(json.load(open('data/v2_5_seed_plan.json'))['stories'].get(str(N), {}), ensure_ascii=False, indent=2))"

# Palette
python3 pipeline/tools/palette.py N --format human --include-grammar

# Step B.1 — forbidden zones
python3 pipeline/tools/forbid.py N

# Step C — would-mint per candidate
python3 pipeline/tools/vocab.py would-mint "候補の日本語"

# Step E — dry-run
python3 pipeline/author_loop.py author N --dry-run

# Step F — live ship (auto runs state_updater + regenerate + audio)
python3 pipeline/author_loop.py author N

# Manual recovery only if a ship was interrupted
python3 pipeline/regenerate_all_stories.py --story N --apply
python3 pipeline/state_updater.py stories/story_N.json
python3 pipeline/audio_builder.py --vocab data/vocab_state.json stories/story_N.json

# One-shot backfills
python3 pipeline/tools/backfill_grammar_intros.py
python3 pipeline/grammar_progression.py

# Test sweep
python3 -m pytest pipeline/tests/ -q

# Inspect a shipped story
python3 pipeline/tools/story.py show N

# §F.3 commit
git add stories/story_N.json pipeline/inputs/story_N.bilingual.json \
        data/vocab_state.json data/grammar_state.json \
        audio/story_N/ audio/words/W*.mp3 state_backups/*.json
git status
git commit -m "Add story N: <title>" && git push
```

---

*Goal: user types `author story N`; clean story ships. If you ever ask the user about rules documented above, re-read §0–§3.*
