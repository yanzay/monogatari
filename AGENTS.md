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
- A bilingual spec (`pipeline/inputs/story_N.bilingual.json`) is the
  AUTHORITATIVE editable source. The shipped `stories/story_N.json` is
  a derived artifact — do NOT hand-edit it.

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

---

## Notes

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
