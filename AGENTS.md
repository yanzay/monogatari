# AGENTS.md — Monogatari workspace memory

This file accumulates concrete, workspace-specific knowledge for future agent
sessions. Keep entries short, factual, and pointed at things that would have
saved a real iteration if known earlier.

---

## Project shape (1-paragraph orientation)

Monogatari is a graded-reader Japanese short-story corpus + reading-app +
authoring pipeline. Stories live in `stories/story_N.json` (built artifact),
authored from `pipeline/inputs/story_N.bilingual.json` (the editable spec).
Vocabulary and grammar progression are tracked in `data/vocab_state.json`
and `data/grammar_state.json`. The pipeline (`pipeline/`) is mature and
includes a deterministic validator, semantic-sanity lints, audio builder,
and an authoring-tools package at `pipeline/tools/`.

---

## Key files & where things actually live

- `pipeline/_paths.py` — **canonical** path discovery and JSON I/O. Use
  `from _paths import load_vocab, load_grammar, load_spec, load_story,
  iter_stories, parse_story_id, write_json, ROOT, STORIES, DATA, INPUTS`.
  Do NOT recompute `ROOT = Path(__file__)...` ad hoc.
- `pipeline/tools/_common.py` — re-exports the above plus `color()`,
  `iter_tokens()`, `build()` (the deterministic converter), `mint_check()`,
  `list_word_occurrences()`. CLIs in `pipeline/tools/` import from here.
- `pipeline/semantic_lint.py` — sentence-level "is this nonsense" rules.
  Numbered 11.x. Each new rule should follow the same `Issue` dataclass
  pattern with `severity` ∈ {`error`, `warning`} and a `location` like
  `"sentence 3"`. Existing rules: 11.1–11.6 (v1), 11.7–11.10 (v2).
- `pipeline/validate.py` — full Checks 1–11 validator; `validate(story,
  vocab, grammar, plan=None)` returns a `ValidationResult` with `.valid`,
  `.errors`, `.warnings`. Check 11 wraps semantic_lint.
- `pipeline/text_to_story.py::build_story(spec, vocab, grammar)` — the
  deterministic converter. Returns `(built_story, build_report)`.
- `pipeline/tools/vocab.py would-mint "<JP>"` — **killer preview tool**:
  returns the words a candidate sentence would silently mint. Always
  consult before drafting any new sentence.
- `pipeline/regenerate_all_stories.py --story N --apply` — the only
  sanctioned way to rebuild a single story's `is_new` flags after a spec
  edit. Use `--dry-run` first to preview cascade.

---

## Vocab/grammar schema gotchas

- `vocab_state.json::words[wid]["first_story"]` is a **string** like
  `"story_1"`, not an int. Use `parse_story_id()` from `_paths.py` to
  coerce. Same applies to `last_seen_story` and grammar `intro_in_story`.
- The "lemma" of a word is its `surface` field (the kanji/kana display
  form), not a separate `lemma` key. The `reading` field is romaji.
- Grammar state file structure: `{"version": ..., "points": {gid: {...}}}`.
  The points dict has `examples` but field names like `label`/`description`/
  `pattern` are inconsistently present.
- **Two parallel grammar id namespaces — reconcile via `catalog_id`.**
  `data/grammar_state.json` keys grammar by internal ids `G001_wa_topic`
  / `G003_desu` / etc. `data/grammar_catalog.json` keys by JLPT-tagged
  ids `N5_wa_topic` / `N5_desu` / etc. The bridge is the `catalog_id`
  field on each grammar_state entry. Coverage analysis (which catalog
  points have been introduced?) MUST join via `catalog_id`. Use
  `pipeline/grammar_progression.coverage_status()` rather than rolling
  your own. The agent_brief and validator both use the helper.
- **`grammar_state.json::points[gid]["intro_in_story"]` is the
  load-bearing field for coverage tracking.** A point with
  `intro_in_story=None` is treated as "not yet covered" by Check 3.10
  / 3.9 / the brief. State_updater sets it on every ship; the
  one-shot `pipeline/tools/backfill_grammar_intros.py` will repair
  legacy bulk-loaded entries that lack it.
- A bilingual spec (`pipeline/inputs/story_N.bilingual.json`) is the
  AUTHORITATIVE editable source. The shipped `stories/story_N.json` is
  a derived artifact — do NOT hand-edit it.
- **Auto-tagged grammar IDs not yet in `grammar_state.json` are
  registered in `text_to_story.KNOWN_AUTO_GRAMMAR_DEFINITIONS`.** Some
  paradigm anchors (most prominently `G055_plain_nonpast_pair`,
  catalog id `N5_dictionary_form`) were never bulk-loaded into
  `data/grammar_state.json`. The tagger emits them whenever a verb
  appears in plain dictionary form, AND the registry carries the
  full state-entry definition (title/short/long/jlpt/catalog_id) so
  `state_updater` can attribute them on first use without a
  hand-written plan. Three loci consult the registry: (1) the
  validator's plan (built by `step_validate` from the build report's
  `unknown_grammar`), (2) the gauntlet's `step_coverage_floor`
  gid→catalog_id fallback, and (3) `_build_state_plan`'s
  `new_grammar_definitions` splice. To add a new auto-tagged paradigm
  anchor: add a token-level `grammar_id` to `_classify_inflection` (or
  another tagger site) AND add a matching entry to
  `KNOWN_AUTO_GRAMMAR_DEFINITIONS`. Regression tests live in
  `pipeline/tests/test_dictionary_form_attribution.py`.

---

## Cascade rules when editing a story

The three things that cascade across the corpus when you change a story:

1. **`new_words` / `new_grammar` flags** — derived from
   `regenerate_all_stories.py`. Rerun after any spec change. Cheap.
2. **`is_new=true` token markers** — same regenerator handles these.
3. **Audio files** — `audio/story_N/*` is per-sentence. Sentence-count
   changes require audio rebuild for that story. **Bounded to one story**
   if other stories' sentences are unchanged.

The thing that does NOT cascade automatically: **other stories' validation**
when an early story removes a grammar/vocab introduction. Verify with
`pytest pipeline/tests/test_validate_library.py -q` after any v1 spec edit.

## Post-ship state chain (now automatic)

**As of 2026-04-28 evening, `pipeline/author_loop.py author N` (live ship,
no `--dry-run`) runs the complete post-ship chain in one shot.** A single
invocation handles:

1. Build + all gauntlet checks (validate, mint_budget,
   pedagogical_sanity, vocab_reinforcement, coverage_floor).
2. Write `stories/story_N.json`.
3. `state_updater` with a plan auto-built from the build report
   (mints W-IDs with full surface/kana/reading/pos/verb_class/adj_class
   metadata). **Hand-written plan JSON files are no longer required** —
   the previous defect of `state_updater scaffolding empty entries
   (surface = "W00xxx")` is impossible because the build report carries
   complete definitions for every mint.
4. `regenerate_all_stories --story N --apply` to rewrite is_new flags
   under final word_ids.
5. `audio_builder` to generate per-sentence and per-word MP3s
   (incremental — re-runs are cheap).

If any of these fails, the gauntlet exits non-zero with a clear
`halted_at: <step>` and `state_backups/` retains the prior
vocab/grammar state for restore. The legacy three-command dance
(`regenerate → state_updater → regenerate`) survives only as a manual
recovery path documented in the SKILL.md "Quick reference" section.

### Re-shipping in the same session

The state-backup discipline below still applies — restoring from a
pre-attempt backup before re-shipping is the safe path when an attempt
attributed grammar that the revised attempt no longer wants.

### Re-shipping after a failed attempt: state-backup discipline

If a story is shipped, then revised and re-shipped in the same
session, the second `state_updater` call does NOT clear attributions
made by the first call. Concretely: if attempt 1 introduced grammar
point G_A and attempt 2 introduces G_B instead, BOTH end up with
`intro_in_story=N` in `grammar_state.json`. The author_loop dry-run
will say "1 new grammar point" (G_B), but the corpus-wide cadence
test `test_grammar_introduction_cadence` will count BOTH and fail
with "introduces 2 new grammar points (max 1 after bootstrap)."

The right recovery is to restore `data/{vocab,grammar}_state.json`
from a pre-attempt state backup (the timestamped files in
`state_backups/`) BEFORE re-shipping the revised story. The
backup taken immediately before the very first `state_updater` of
the session is the safe restore point; later backups carry the
contamination.

### Audio cleanup after an ID-changing re-ship

`pipeline/audio_builder.py` writes per-sentence (`s0.mp3` …) AND
per-word (`w_W00xxx.mp3`) files. If a re-ship changes word IDs (e.g.
because the previous attempt's W00xxx got dropped as an orphan and
the next mint reused the slot at a different position), stale
`w_W*.mp3` files become orphans and the integrity test
`test_audio_word_files_only_for_known_words` fails. After an
ID-changing re-ship, either rebuild from a clean `audio/story_N/`
directory or hand-delete the stale `w_W*.mp3` files whose IDs are
no longer in `data/vocab_state.json`.

### Per-story vocabulary cadence has BOTH a max AND a min

The mint_budget surfaced in the brief is `{min, max, target}` for a
reason — both bounds matter. The gauntlet's `mint_budget` step only
enforces the max; the corpus-wide test
`test_vocabulary_introduction_cadence` enforces the min
(`MIN_NEW_WORDS_PER_STORY = 3` after bootstrap). A dry-run that
ships a single new word will pass the gauntlet AND fail the test
suite. Always read the brief's `mint_budget.min` as a hard floor,
not a soft suggestion.

### Dry-run green ≠ corpus tests green

The gauntlet pulls SOME pedagogical checks forward
(`pedagogical_sanity`, `coverage_floor`, `mint_budget`), but several
corpus-wide rules still only fire under `pytest pipeline/tests/`:

- `test_vocabulary_introduction_cadence` (per-story min new words)
- `test_vocab_words_are_reinforced` (per-word reinforcement window)
- `test_grammar_introduction_cadence` (per-story max new grammar)
- `test_audio_word_files_only_for_known_words` (audio orphans)

Always run `pytest pipeline/tests/ -q` after the post-ship chain.
Dry-run green is necessary but not sufficient.

---

## Critical workflow lessons learned 2026-04-28

### Edit a single early story → may cascade many stories
When trimming/rewriting an early story's spec, the user warned this
correctly: any vocab dropped that was the *only* source of a later
grammar reinforcement breaks downstream. Before rewriting story N,
run `lookup.py --reuse-preflight` (if available) or grep
`grep -l "G0XX_" stories/story_*.json | head` to find the *next*
story that still relies on each grammar point N introduces.

### `would-mint` from `pipeline/tools/vocab.py` is the right preflight
Avoid the multi-iteration "draft → tokenize → discover I introduced 同じ
which doesn't exist yet" loop by using `vocab.py would-mint` BEFORE
committing a candidate sentence to a spec. Each iteration of that loop
is a wasted ~3 tool calls.

### `pipeline/inputs/story_N.bilingual.json` is the only file to edit
Never rewrite `stories/story_N.json` directly. Always edit the spec,
run `regenerate_all_stories.py --story N --apply`, then validate.

### Existing tooling is far more comprehensive than first appears
The `pipeline/tools/` package and `pipeline/lookup.py` together cover
~80% of authoring-support needs already. Always inventory the existing
tools (`ls pipeline/tools/ && head pipeline/lookup.py`) before
proposing new ones.

### Conservatism in lint design is documented and intentional
`semantic_lint.py`'s `INANIMATE_QUIET_NOUN_IDS` deliberately **excludes**
雨/月/星/空/風 because the author considers these natural JP pathetic-
fallacy. When proposing rule changes, respect existing exclusion lists
and module-level docstrings — they encode native-speaker calls that
overrule audit findings.

### v1 is RETIRED — only v2 stories live in `stories/`
The v1 corpus has been moved to `legacy/v1-stories/` and the
`V1_INCOMPATIBLE_WITH_V2_LINTS` xfail set in
`pipeline/tests/test_validate_library.py` has been **deleted**. Every
story in `stories/` must pass the full validator (Checks 1–11) cleanly
— there are no expected-failure escape hatches. If a v1 motif tempts
you, port the idea into a v2 spec via `pipeline/author_loop.py author
N`; do not resurrect a v1 file.

---

## Shell quirks observed

- `cd pipeline/tools && python3 ...` sometimes fails because the bash
  tool's CWD doesn't persist across invocations as expected. **Always
  invoke scripts with their full path from project root**:
  `python3 pipeline/tools/palette.py ...` (no cd).
- The project uses `.venv/`. Always prepend `source .venv/bin/activate &&`
  to commands that import `fugashi`/`jaconv`/`jamdict`. The bare
  `/opt/homebrew/.../python3.14` will fail with "fugashi/jaconv/jamdict
  are required."

---

## v2 architectural commitments (active as of 2026-04-28)

v1 has been retired (`legacy/v1-stories/`). v2 is the only path. Key
commitments documented in `docs/v2-strategy-2026-04-27.md` and
`docs/phase3-tasks-2026-04-28.md`:

- **Author = LLM agent.** No hand-authoring of stories. The agent
  drafts a bilingual spec and runs `pipeline/author_loop.py author N`.
- **Deterministic lints are HARD BLOCK.** Validate (Checks 1–11),
  mint_budget, and pedagogical_sanity all hard-fail the gauntlet.
  Only the LLM literary reviewer is best-effort + warn.
- **The gauntlet steps (in order):** spec_exists → agent_brief →
  build → validate → mint_budget → pedagogical_sanity →
  literary_review (stub) → write → audio (stub). The
  `pedagogical_sanity` step pulls the test_introduced_grammar_is_reinforced
  check forward into the gauntlet so reinforcement debt is caught at
  dry-run, not after shipping.
- **The brief is the agent's only memory.** Always read it once, fully,
  before drafting. Key fields: `mint_budget`, `grammar_reinforcement_debt`
  (especially `must_reinforce: true` items), `previous_closers` (don't
  clone a closing pattern), `previous_3_stories`, `north_stars`,
  `anti_patterns_to_avoid`.
- **Override discipline:** logged soft override; same rule overridden
  3× auto-suspends and escalates to human.
- **Required spec fields (v2):** `intent`, `scene_class`, `anchor_object`,
  per-sentence `role` ∈ {setting, action, dialogue, inflection,
  reflection, closer}.
- **Recurring human audit every 10 stories** because reviewer model is
  same family as author (shared blind-spot risk).
- **Per-story grammar floor (added 2026-04-28).** Every post-bootstrap
  story (story 4+) MUST introduce ≥1 new grammar point until the
  current JLPT tier is fully covered (then the same rule for N4, then
  N3). Validator Check 3.10 + gauntlet `coverage_floor` step
  hard-block any story that violates this. The brief surfaces the
  uncovered list under `grammar_introduction_debt`. Tier advancement
  (e.g. story 11 → N4) requires every prior-tier point to be covered
  first (Check 3.9). Coverage status today: see
  `python3 pipeline/grammar_progression.py`.

---

## Notes

### Standing user preference: auto-commit and push after a clean ship
As of 2026-04-28, the user gave a permanent instruction: "commit and
push, do not ask ever again." For any clean ship of a Monogatari story
(gauntlet `VERDICT: ship`, full pytest green, F.2 self-review pass),
proceed directly to `git add … && git commit … && git push` WITHOUT
asking for confirmation. The Proactivity Guidelines' default to confirm
write operations is overridden for git in THIS workspace. This applies
to all future story authoring sessions.

### When the user says "rewrite story N and run tests, then restore"
Take backups to `/tmp/` BEFORE editing, do the work, then restore from
backups and re-verify tests at the end. The user means it literally.
Pattern that worked:

```bash
cp pipeline/inputs/story_N.bilingual.json /tmp/story_N.bilingual.json.bak
cp stories/story_N.json /tmp/story_N.json.bak
# ...do work...
cp /tmp/story_N.bilingual.json.bak pipeline/inputs/story_N.bilingual.json
cp /tmp/story_N.json.bak stories/story_N.json
python3 -m pytest pipeline/tests/ -q
```

### When the user is venting about quality and asking "what to do"
The user has put real effort into this project; defects feel personal.
The right move is: (1) acknowledge the frustration honestly without
fawning, (2) gather evidence before promising a plan, (3) propose
something **bounded** rather than "rebuild from scratch," (4) explicitly
flag the implications of choices that look reasonable but aren't (e.g.
"default retire" + "best-effort + warn" together is a hidden quality
regression).

### Parallel subagents are great for "read N stories with the same rubric"
Three subagents reading 19 stories each in parallel gave a far better
audit than one agent reading 56 sequentially — and the rubric convergence
across independent agents is itself signal. Use this pattern for any
"survey the whole corpus / repo / dataset" task.
