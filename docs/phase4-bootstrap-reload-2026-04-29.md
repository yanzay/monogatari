# Monogatari Phase 4 — Bootstrap Reload

**Status:** Plan, awaiting sign-off then immediate execution in the same
session (per user directive 2026-04-29 18:20).

**Triggered by:** the convergence diagnosis in this session (10
consecutive ships of essentially the same story) + the in-skill
literary-review discipline that landed earlier today (SKILL §B.0/B.1/
§E.5/E.6/E.7/§G).

**Decision being committed:** the v2.0 corpus (stories 1–10) is being
deleted from `stories/` and `pipeline/inputs/`, and the v2/v2.0 vocab
+ grammar state is being reset to an empty baseline. The corpus is
re-authored from scratch under a new front-loaded bootstrap ladder + a
prescriptive diversity-seed plan, with the new in-skill discipline as
the literary gate.

git history retains the v2.0 corpus; no archive folder is created.

---

## §1. Why we're doing this

The 2026-04-27 audit (`docs/audit-2026-04-27.md`) identified that the
v1 corpus had converged on a small set of motifs because the early
vocabulary ladder lacked concrete colors, spatial words, dialogue
verbs, and concrete action verbs — forcing every story into "narrator
observes object" shapes. Phase 3 (v2) acknowledged this and shipped
the lints + the gauntlet, but **kept the existing word ladder** and
shipped 10 v2 stories under it. They convergence-failed identically:
3 anchors used twice, 6/10 set in a park, 8/10 with the same
hand-over event shape, "warm egg on the road" type oddities passing
because nothing in the pipeline checks plot plausibility.

The defect wasn't agent imagination; **it was the seed**. With ~50
words biased toward small-object handover, the only stories the
vocabulary could express were small-object-handover stories.

This phase fixes the seed.

---

## §2. The two changes that have to land together

This phase makes **two** correlated changes. Either alone would fail
in a different way; only together do they actually fix the bootstrap.

### Change A — Replace `BOOTSTRAP_END = 3` with a **per-story ladder** for stories 1–10

Today's policy is essentially "trickle in vocab + grammar at the
steady-state rate from story 4 onward." That treats the bootstrap as
a contracted version of the steady state. Wrong: the bootstrap's job
is *establishing the plot-space the corpus will live in*, which has
different right answers from steady-state maintenance.

The new policy is an explicit per-story ladder that **front-loads
both vocab AND grammar** in stories 1–10, then collapses to today's
steady-state rules at story 11.

### Change B — Replace "open" mint budgets with a **prescriptive seed plan**

Lifting the caps without prescribing what fills them just produces
opportunistic mints (the agent picks "warm + egg" because they fit
the sentence). The reload pairs the new caps with `data/v2_5_seed_plan.json`,
which **prescribes specific words and grammar points to specific story
slots**. The agent's brief surfaces these as `must_mint_from_seed`,
hard-blocked by the gauntlet.

The seed plan is derived from:
1. The audit's §4 "Budget regrets" table — the specific words flagged
   as missing-too-late.
2. The N5 catalog (54 entries) targeted to be fully covered by story
   ~12 — i.e. ~4.5 grammar points per story average across stories
   1–12.
3. A scene plan that explicitly heterogenises stories 1–10 across 10
   different `scene_class` values, so `forbid.py` (just landed) never
   has to bite.

---

## §3. The new per-story ladder

Replaces the constants in `pipeline/grammar_progression.py`:

| Story | vocab_min | vocab_max | grammar_min | grammar_max | scene_class |
|---|---|---|---|---|---|
| 1  | 14 | 18 | 6 | 8 | home_morning |
| 2  | 6  | 10 | 3 | 5 | walk_to_shop |
| 3  | 5  | 8  | 3 | 4 | kitchen |
| 4  | 5  | 8  | 2 | 4 | classroom |
| 5  | 4  | 7  | 2 | 4 | station |
| 6  | 4  | 7  | 2 | 3 | park_bench |
| 7  | 4  | 6  | 2 | 3 | rainy_doorway |
| 8  | 3  | 6  | 1 | 3 | shop_counter |
| 9  | 3  | 5  | 1 | 2 | phone_call |
| 10 | 3  | 5  | 1 | 2 | rooftop |
| 11+ | 3 | 5 | 1 | 1 | (steady state — no constraint) |

Cumulative by end of story 10: **~52 words** (vs ~50 currently — small
absolute change, large compositional change because they're *the right
words*) and **~28 grammar points** (vs ~12 currently — the real lift).

That puts story 10 at ~52% N5 coverage and pushes "complete N5" to
story ~12 (target met).

### Notes on the ladder's shape

- **Story 1 cold-start is wider than current.** The current story 1
  shipped with 11 mints + 6 grammar; the new ladder allows 14–18 mints
  + 6–8 grammar. This is to land a complete starter palette in one
  shot rather than rationing across stories 1–3.
- **`grammar_min ≥ 2` for stories 2–7.** The single-grammar floor is
  what makes the agent ration grammar over the arc. Forcing 2+ in
  these stories means the agent must *combine* grammar points within
  a single story — which is where non-trivial sentence shapes come
  from.
- **The taper to (1,1) at story 11 is intentional.** After story 11
  the steady-state policy resumes; this is what `MAX_NEW_PER_STORY=1`
  in `grammar_progression.py` will continue to enforce.
- **Vocab caps are above today's `MAX_NEW_PER_STORY` for stories 1–7.**
  The cap goes 18→10→8→8→7→7→6, a controlled descent.

### The reinforcement-window math still works

R1 (`VOCAB_REINFORCE_WINDOW = 10`) requires every minted word to
reappear in the next 10 stories. Under the new ladder:
- Story 1's 14–18 mints have stories 2–11 to land in (10 follow-ups,
  total ~50 word slots available — easy fit).
- Story 2's 6–10 mints have stories 3–12 (10 follow-ups, ~40 slots —
  still loose).
- The taper means by story 8 there's almost no R1 pressure left from
  the front-loading.

If R1 ever does tighten, the ladder's max can be lowered for that
story; nothing downstream breaks because the ladder is data, not
hard-coded.

---

## §4. The diversity-seed vocab plan

For each story 1–10 the plan prescribes a **must-mint set** (the
specific lemmas the slot must introduce) and an **encouraged-from**
set (lemmas the slot may opportunistically pull from if scene/grammar
demand). All other mints count as opportunistic and trigger a §G
override.

The full seed table lives in `data/v2_5_seed_plan.json` (Phase 2
authors that file). Below is the human summary.

### Story 1 — `home_morning` — anchor: 鍵 (key)
**must-mint (16):** 私 (I), 朝 (morning), 家 (house), 部屋 (room),
ドア (door), 鍵 (key), 手 (hand), テーブル (table), パン (bread),
お茶 (tea), 食べる (eat), 飲む (drink), 開ける (open), 持つ (hold),
小さい (small), 大きい (big)
**must-grammar (7):** N5_wa_topic, N5_wo_object, N5_ga_subject,
N5_ni_location, N5_de_means, N5_masu, N5_i_adj

### Story 2 — `walk_to_shop` — anchor: 傘 (umbrella)
**must-mint (8):** 行く (go), 歩く (walk), 道 (road), 雨 (rain),
傘 (umbrella), さす (raise/use umbrella), 友達 (friend), 一緒に (together)
**must-grammar (4):** N5_to_and (と connecting nouns), N5_e_direction (へ),
N5_kara_from, N5_made_until

### Story 3 — `kitchen` — anchor: 卵 (egg)
**must-mint (7):** 母 (mother), 台所 (kitchen), 卵 (egg), 牛乳 (milk),
作る (make), 切る (cut), 暖かい (warm)
**must-grammar (4):** N5_mashita (past), N5_masen (negative),
N5_masen_deshita (past negative), N5_kosoado (これ/それ/あれ)

### Story 4 — `classroom` — anchor: 本 (book)
**must-mint (7):** 学校 (school), 教室 (classroom), 先生 (teacher),
本 (book), 鉛筆 (pencil), 読む (read), 書く (write)
**must-grammar (3):** N5_ka_question, N5_dare_who, N5_nan_what

### Story 5 — `station` — anchor: 切符 (ticket)
**must-mint (6):** 駅 (station), 電車 (train), 切符 (ticket),
時計 (clock/watch), 待つ (wait), 来る (come)
**must-grammar (3):** N5_te_form, N5_te_kudasai (please do), N5_itsu_when

### Story 6 — `park_bench` — anchor: 手紙 (letter)
**must-mint (6):** 公園 (park), 椅子 (bench/chair), 木 (tree),
手紙 (letter), 座る (sit), 立つ (stand)
**must-grammar (3):** N5_mo_also (も), N5_te_imasu (progressive/state),
N5_aru_iru (revisit canonical)

### Story 7 — `rainy_doorway` — anchor: 靴 (shoes)
**must-mint (5):** 靴 (shoes), 玄関 (entryway), 濡れる (get wet),
寒い (cold), 入る (enter)
**must-grammar (2):** N5_kara_because (clause-から), N5_demo (sentence-でも)

### Story 8 — `shop_counter` — anchor: 花 (flower)
**must-mint (5):** 店 (shop), 花 (flower), お金 (money), 円 (yen unit),
買う (buy)
**must-grammar (2):** N5_counters, N5_ikura (how much)

### Story 9 — `phone_call` — anchor: 声 (voice)
**must-mint (4):** 電話 (telephone), 声 (voice), 言う (say),
聞く (hear/ask)
**must-grammar (2):** N5_to_quote (と言う direct quote), N5_dictionary_form

### Story 10 — `rooftop` — anchor: 星 (star)
**must-mint (4):** 屋上 (rooftop), 空 (sky), 星 (star), 見える (be visible)
**must-grammar (2):** N5_ga_but (clause-が contrast), N5_hoshii (want)

### Cumulative by story 10
- ~70 unique words (above the §3 ladder min, well within max)
- ~32 N5 grammar points = ~59% of the 54-point N5 catalog
- 10 distinct scenes, 10 distinct anchors

The remaining ~22 N5 grammar points land in stories 11–14 under the
steady-state policy (still within "complete N5 by story ~14" — slightly
over the §2 stretch goal of 12, comfortably within the audit's
recommended pace).

---

## §5. The scene-affordances data file

`data/scene_affordances.json` lists, for each scene, the nouns that
naturally live there. The brief surfaces this as `scene_palette` for
the planned scene of the next story, so the agent doesn't have to
guess "what nouns go in a kitchen?" — the answer is derived from
the seed plan + the affordances table.

This file ALSO unblocks future stories (11+): once N5 is closed and
the per-story floor relaxes, the agent can pick from `unused_scenes`
to keep the corpus diverse.

Initial scenes covered in Phase 4:
- `home_morning`, `walk_to_shop`, `kitchen`, `classroom`, `station`,
  `park_bench`, `rainy_doorway`, `shop_counter`, `phone_call`, `rooftop`,
  `train_window`, `hospital_visit`, `library`, `bedtime`, `garden_dusk`,
  `bus_ride`

---

## §6. What the new SKILL discipline catches that the old ladder couldn't

The literary discipline landed earlier today (SKILL §B.0/B.1/§E.5/E.6/
E.7/§G) is necessary but not sufficient on its own — with a tight
palette, the prosecutor pass at §E.5 can only catch shape defects, not
lexical poverty. Pairing the discipline with the new ladder + seed
plan gives both legs:

| Failure mode | Caught by |
|---|---|
| "park-walk-pickup" loop (lexical poverty) | Seed plan (different scene + anchor per story) |
| "noun-pile closer" (shape) | §E.5 prosecutor pass + Lint 11.7 |
| "warm egg on a road" (implausibility) | Scene-affordances table flags non-listed (noun, scene) pairs |
| "convergence to last story" (rhythm) | §B.1 forbid.py + §E.7 fresh-eyes subagent |
| "rationalize 'no' into 'yeah but'" | §G override budget |

Both legs land together. The deletion in §9 is committed against this
combined discipline, not against the new ladder alone.

---

## §7. What is explicitly NOT changing

- **R1 reinforcement window** (`VOCAB_REINFORCE_WINDOW = 10`,
  `min_uses = 1`) — stays. The new ladder respects it.
- **Cross-tier guard** (Check 3.5) — stays. Bootstrap is N5-only.
- **Tier advancement gate** (Check 3.9) — stays. Story 11+ may not
  enter N4 until N5 is complete.
- **The gauntlet's deterministic steps** — `validate`, `mint_budget`,
  `pedagogical_sanity`, `vocab_reinforcement`, `coverage_floor`. Each
  reads the new ladder data; no algorithmic change.
- **The in-skill literary discipline** — landed today, untouched.
- **The forbid.py tool** — landed today, untouched.
- **`step_audio` and `step_write`** — untouched.
- **Validator semantic lints (Check 11.1–11.10)** — untouched.

---

## §8. Code changes (Phase 2 of the execution)

In dependency order:

1. **`pipeline/grammar_progression.py`** — add `BOOTSTRAP_LADDER` table
   (per-story `(vocab_min, vocab_max, grammar_min, grammar_max,
   scene_class)`); keep `BOOTSTRAP_END=10`; add `ladder_for(story_id)`
   helper; deprecate `MIN_NEW_WORDS_PER_STORY` constant in favor of
   `ladder_for(n).vocab_min` (constant kept for back-compat).
2. **`data/v2_5_seed_plan.json`** — author the prescriptive per-story
   seed (lemmas + grammar IDs).
3. **`data/scene_affordances.json`** — author the scene palette table.
4. **`pipeline/tests/test_pedagogical_sanity.py`** —
   `test_grammar_introduction_cadence` reads the ladder instead of
   `MAX_NEW_PER_STORY`; `test_vocabulary_introduction_cadence` reads
   the ladder for vocab min.
5. **`pipeline/tools/agent_brief.py`** — surface `ladder` and
   `seed_plan` for the next story under `must_hit.seed_plan` and
   `must_hit.ladder`.
6. **`pipeline/author_loop.py`** — `step_mint_budget` reads the
   ladder's vocab range; `step_coverage_floor` reads grammar_min/max.
7. **`pipeline/tools/cadence.py` + `pipeline/tools/weave.py`** — read
   ladder, not `BOOTSTRAP_END`-as-int.
8. **`.agents/skills/monogatari-author/SKILL.md`** — link to this
   plan; add §A.5 "Read seed-plan slot for this story"; update §C
   "Mint budget" → "the budget is prescribed, not declared."

---

## §9. The destructive reset (Phase 3 of the execution)

In strict order; each step's success is a precondition for the next:

1. `git status` clean check; refuse to proceed if dirty (other than
   the Phase 2 edits, which are the working tree).
2. **Snapshot commit**: `Snapshot v2.0 corpus before v2.5 reload`.
   Includes Phase 1 + Phase 2 changes so the boundary is obvious in
   the log.
3. Delete `stories/story_{1..10}.json` (10 files).
4. Delete `pipeline/inputs/story_{1..10}.bilingual.json` (10 files).
5. Delete `audio/story_{1..10}/` (10 directories with ~60 mp3 files).
6. Delete `audio/words/W*.mp3` (~42 files; all current W-IDs go away).
7. Reset `data/vocab_state.json`:
   ```json
   {"version": 2, "updated_at": null, "last_story_id": 0,
    "next_word_id": "W00001", "words": {}}
   ```
8. Reset `data/grammar_state.json` so every entry's `intro_in_story`
   becomes `null`. Preserve titles, prerequisites, catalog_id mapping
   (the catalog itself is not corpus-derived).
9. `python3 pipeline/regenerate_all_stories.py --apply` — rebuilds
   `static/data/index.json` to empty.
10. `pytest pipeline/tests/ -q` — most tests should pass on an empty
    corpus (cadence tests are vacuous on N=0). Any over-asserting
    test gets fixed in place.
11. **Reset commit**: `v2.5 reload: clear corpus + reset state to seed-plan baseline`.

---

## §10. Validation gates

The reload is not "done" the moment it's executed. It's done when:

- **After story 5 ships:** corpus-anchor-diversity check — no anchor
  used twice in stories 1–5; no scene_class used twice. If either
  fails, halt and replan.
- **After story 10 ships:** mini-audit (one fresh-eyes subagent reads
  all 10 specs, applies the same rubric the 2026-04-27 audit used,
  reports SHIP/REWRITE-SENTENCE/REWRITE-STORY counts). Target: ≥80%
  SHIP, 0% REWRITE-STORY. If we fall short, the ladder + seed plan
  get retuned before story 11.
- **At every ship:** the new in-skill discipline (§B.0/B.1/§E.5/E.6/
  E.7/§G) runs as documented. Override budget ≤1 per session.

---

## §11. Effort estimate

- Phase 1 (this doc): done as you read it.
- Phase 2 (code changes): ~2 hours.
- Phase 3 (destructive reset): ~15 min, irreversible without git.
- Phase 4 (re-author stories 1–10): ~2 hours/story × 10 = 20 hours of
  agent time, spread across many sessions. Not in this session.

This session ends at the reset commit.

---

## §12. Cascade-trap mitigations baked in

The 2026-04-28 evening session's hard-won lessons (AGENTS.md "Lessons
learned 2026-04-28 evening") apply to the reload:

- **State backups discipline**: every author_loop ship snapshots
  `data/{vocab,grammar}_state.json` to `state_backups/`. The reset
  commit is the implicit "fresh baseline" snapshot.
- **Audio cleanup discipline**: §9 step 6 deletes ALL `audio/words/`
  files because every W-ID is being re-minted. The integrity test
  `test_audio_word_files_only_for_known_words` will pass on an empty
  audio set.
- **Reconcile grammar state discipline**: not needed at reset time
  (state is empty); becomes relevant from story 1 onward via the
  per-story `regenerate_all_stories --story N --apply` path inside
  `step_write`.
- **Orthographic consistency** (hiragana for grammaticalized verbs):
  encoded in the seed plan — the seed prescribes hiragana forms for
  ある/いる/する etc. so the inconsistency that bit stories 9 and 10
  cannot recur.

---

*Plan drafted 2026-04-29 18:21. Execution begins immediately upon
sign-off.*
