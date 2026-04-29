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

`pipeline/audio_builder.py` writes per-sentence audio to
`audio/story_<N>/s<idx>.mp3` and per-word audio to a FLAT
`audio/words/<wid>.mp3` directory (changed 2026-04-29; see
"Audio layout" below). If a re-ship changes word IDs (e.g. because
the previous attempt's W00xxx got dropped as an orphan and the next
mint reused the slot at a different position), stale
`audio/words/W*.mp3` files become orphans and the integrity test
`test_audio_word_files_only_for_known_words` fails. After an
ID-changing re-ship, hand-delete the stale `audio/words/W*.mp3`
files whose IDs are no longer in `data/vocab_state.json`.

### Audio layout (since 2026-04-29)

- `audio/story_<N>/s<idx>.mp3` — per-sentence audio. Story-scoped,
  because a sentence belongs to exactly one story.
- `audio/words/<wid>.mp3` — per-word audio. **Flat, decoupled from
  any story.** A word can appear in any number of stories and in
  the vocab list, library, review queue, and word popups opened
  from any context — tying its audio path to the introducing story
  made the audio undiscoverable from those contexts and broke
  whenever a corpus rewrite changed which story introduces a word.
  The migration moved 42 existing files from
  `audio/story_<N>/w_W*.mp3` → `audio/words/W*.mp3` and updated
  every consumer in lockstep:
    - `pipeline/audio_builder.py` writes to `words_dir`
    - `pipeline/tests/test_referential_integrity.py` orphan test
      checks `audio/words/` and rejects stray `audio/story_*/w_*.mp3`
    - `src/lib/util/word-audio.ts::wordAudioPath` returns the new
      flat path and no longer needs `first_story`
    - `src/lib/data/corpus.ts::decorateWithAudioPaths` synthesizes
      the flat path
- The legacy per-story word audio in `legacy/v1-audio/story_*/` is
  intentionally left in place; v1 is retired and self-contained.

### Per-story vocabulary cadence has BOTH a max AND a min

The mint_budget surfaced in the brief is `{min, max, target}` for a
reason — both bounds matter. The gauntlet's `mint_budget` step only
enforces the max; the corpus-wide test
`test_vocabulary_introduction_cadence` enforces the min
(`MIN_NEW_WORDS_PER_STORY = 3` after bootstrap). A dry-run that
ships a single new word will pass the gauntlet AND fail the test
suite. Always read the brief's `mint_budget.min` as a hard floor,
not a soft suggestion.

### Story 2 (2026-04-29) shipped without §B.0/§B.1/§E.5/§E.6/§E.7

For honesty: story 2 (`小さいりんご`, commit e7f0556) was shipped
having ONLY run the retired §F.2 self-audit — the in-skill literary
gates (§B.0 premise contract, §B.1 forbid.py mechanical zones, §E.5
prosecutor table, §E.6 EN-only re-read, §E.7 fresh-eyes subagent)
were all skipped. The user noticed and asked. The discipline was
backfilled post-hoc:
  * `.author-scratch/prosecution_2.md` written retroactively (all rows
    Y, including the §B.0 contract checks reconstructed from the
    actual spec).
  * `pipeline/tools/forbid.py 2` ran clean (all four zones organically
    honored).
  * §E.7-equivalent fresh-eyes subagent returned `SHIP` with the
    same key findings as the prosecutor table.

The corpus is fine because the story genuinely satisfies all gates,
but the audit trail was incomplete until the backfill. The skill
(`SKILL.md`) was patched in the same exchange to add §0.0 (the
top-level full ordered procedure list) and two ⛔ STOP callouts at
the §E→§E.5 and §E.7→§F transitions, so the literary gates are
impossible to skip on a normal scan.

If you find yourself activating the skill and your activation
summary stops at "Step F — Ship," you've fallen into the same trap.
Re-read §0.0 and §E.5–§E.7 before drafting.

### vocab_reinforcement gauntlet step is "last-slot only" since 2026-04-29

The gauntlet's `vocab_reinforcement` step (in `pipeline/author_loop.py`)
is BACKED by `_vocab_reinforcement_debt()` in `pipeline/tools/agent_brief.py`,
which decides which words are `must_reinforce` (hard-block) vs
`should_reinforce` (warn). The original rule (2026-04-28) flagged EVERY
word minted in story N-1 as must-reinforce for story N — which forced
story 2 to recycle every one of story 1's ~18 mints (impossible without
turning the story into a list of nouns).

Relaxed 2026-04-29 to mirror the post-ship test's actual contract:

  * `must_reinforce=True` ONLY when the R1 window
    (`VOCAB_REINFORCE_WINDOW = 10`) is about to close on the word —
    i.e. `target_story == intro_story + VOCAB_REINFORCE_WINDOW` AND no
    follow-up has used the word yet.
  * Words intro'd during the bootstrap window (`intro_story <=
    BOOTSTRAP_END = 10`) NEVER become must_reinforce. R1 itself
    exempts bootstrap-intro stories (`if n <= BOOTSTRAP_END: continue`),
    so the gauntlet matches.
  * Everything else in-window-but-not-last-slot is `should_reinforce`
    (informational, non-blocking). The author still sees the
    "due soon" hints in the brief; the gauntlet just doesn't block.

The post-ship test `test_vocab_words_are_reinforced` (R1) is
unchanged. It remains the source of truth for what "reinforced" means.

Practical consequence for an authoring session: the next story after
a wide-mint slot (e.g. story 1 → story 2) only needs to reuse the
words that fit the scene's narrative, not every word from the
previous story. Pick organic reuse (3-6 carryover words is normal),
let the rest get reinforced over the natural 10-story curve.

DO NOT re-tighten this rule without also relaxing R1 itself. The
old "every prev-story word must reappear next story" rule directly
contradicted R1 and made bootstrap follow-ups unshipable.

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

## Lessons learned 2026-04-28 evening (audit + 3-story rewrite cycle)

### G055_plain_nonpast_pair (relative-clause plain-form verbs) is a cascade trap

Twice in one session, an attempt to introduce `G055_plain_nonpast_pair`
in a story 4–7 (via a relative clause like 「読む紙」 / 「卵を持つ友達」)
failed the corpus-wide `test_introduced_grammar_is_reinforced` because
NO story 4–10 currently uses any verb in plain dictionary form. Each
attempt led to one of two cascade failures:

1. **Add a downstream relative clause to story N+1** to satisfy
   reinforcement → that downstream story now has 2 new grammar points
   (its original intro + G055), which violates `test_grammar_introduction_cadence`
   (max 1 after bootstrap).
2. **Introduce in story N AND ALSO add a different downstream sentence**
   to absorb it → spirals into 3+ story edits per attempt.

**Rule:** Do NOT introduce `G055_plain_nonpast_pair` (or any other
auto-tagged grammar point with no downstream usage) until at least
ONE story 5–10 already organically uses the construction. Today the
corpus has zero plain-form verb usage anywhere — G055 is effectively
locked behind a story 11+ first introduction. The brief's
recommended[0] = N5_dictionary_form is misleadingly high-priority;
treat it as a stretch goal that requires planning across ≥2 stories
in advance.

The general form of this rule: **Before introducing any grammar point
G in story N, grep `stories/story_{N+1..N+5}.json` for at least one
token whose `grammar_id == G`.** If none, deferring is cheaper than
the cascade.

### grammar_state.intro_in_story drifts from corpus first-use after rewrites

Every time a story is re-shipped (especially after spec edits to s0
or early sentences that change WHICH story first uses a particle/
construction), the `intro_in_story` field in `data/grammar_state.json`
can drift from the actual corpus first-occurrence. The
`state_updater` doesn't reset existing attributions; the regenerator
uses one rule, the validator another. Symptom: pytest reports that
story N "introduces 2 new grammar points" when a rewrite shifted one
intro from N+k back to N.

**Fix:** A reconciliation pass that walks all 10 stories in order,
records the FIRST story_id each grammar_id appears in, and rewrites
`intro_in_story` to match (clearing entries that no longer appear
anywhere in the corpus to None). The inline script used three times
this session:

```python
import json
g = json.load(open('data/grammar_state.json'))
first_use = {}
for n in range(1, 11):
    s = json.load(open(f'stories/story_{n}.json'))
    for sec_name in ['title']:
        for tok in (s.get(sec_name) or {}).get('tokens', []):
            for gid in [tok.get('grammar_id'),
                        (tok.get('inflection') or {}).get('grammar_id')]:
                if gid and gid not in first_use:
                    first_use[gid] = n
    for sent in s.get('sentences', []):
        for tok in sent.get('tokens', []):
            for gid in [tok.get('grammar_id'),
                        (tok.get('inflection') or {}).get('grammar_id')]:
                if gid and gid not in first_use:
                    first_use[gid] = n
for gid in list(g['points'].keys()):
    if gid not in first_use and g['points'][gid].get('intro_in_story') is not None:
        g['points'][gid]['intro_in_story'] = None
for gid, n in first_use.items():
    if gid in g['points']:
        g['points'][gid]['intro_in_story'] = n
json.dump(g, open('data/grammar_state.json','w'), indent=2, ensure_ascii=False)
```

This script should be folded into a `pipeline/tools/reconcile_grammar_state.py`
CLI in a future session — the inline form is fine for now but every
rewrite session needs it. Always run AFTER `regenerate_all_stories.py
--apply` and BEFORE the final pytest, then run regenerate ONE MORE
TIME so the per-story `new_grammar` arrays match the reconciled state.

### Closer cliché ladder needs ongoing curation, not just §C.2

Three-pass observation: as new fresh closer patterns get used, they
themselves become clichés after 2–3 stories. The current corpus has
sub-templates emerging:

- `Nは[i-adj]です` as closer (story 3 「卵は暖かいです」, story 7
  「紙は古いです」). Two uses. Becomes a banned ladder entry on the
  next i-adj-attribute closer.
- Departure-walks (story 4 「友達は朝の道を歩きます」). One use.
  Banned for stories 5–9.
- Listing-と reflection (「N₁とN₂は…です」). Used in story 4
  reflection. Variants OK; same-shape repeats banned.

**Rule:** When proposing a closer, scan the previous 3 stories'
closers for shape (not just surface). If your closer matches the
SHAPE (subject-particle-attribute-copula, possessive-departure-verb,
listing-equivalence, etc.), rotate.

### Re-ship discipline (extends AGENTS.md state-backup section)

If a re-ship attempt fails AND it minted new vocab AND it attributed
new grammar, the cleanup chain is:

1. Restore `data/{vocab,grammar}_state.json` from the pre-attempt
   backup in `state_backups/` or `/tmp/`.
2. Hand-delete stale `audio/story_N/w_W*.mp3` files for IDs that no
   longer exist in vocab_state.
3. Hand-delete stale `audio/story_N/sX.mp3` files where X exceeds
   the new sentence count.
4. Re-ship the revised story.
5. Run the reconciliation script above.
6. `regenerate_all_stories.py --apply`.
7. `audio_builder.py` for any story whose sentence text changed.
8. Full pytest sweep.

This whole chain has run cleanly three times in a row this session
following this exact ordering.

### Orthographic consistency: prefer hiragana for grammaticalized verbs

Stories 9 and 10 originally used `有ります` (kanji) where stories 1–8
used `あります` (hiragana). For grammaticalized existence verbs (ある,
いる, なる, できる, etc.), the corpus convention is HIRAGANA. The
spec's source-of-truth is the bilingual.json; sed-normalize in place
when drift is detected:

```bash
sed -i.tmp 's/有ります/あります/g' pipeline/inputs/story_*.bilingual.json
rm pipeline/inputs/*.tmp
```

Then regen + audio rebuild for the affected stories.

### No-obscure-kanji mint guard (since 2026-04-29 evening)

The minted vocab `surface` field is what the review screen, vocab list,
and word popups display to learners. Historically `_ensure_word` in
`pipeline/text_to_story.py` used the UniDic *lemma* (which prefers
kanji canonical forms) as the surface, even when the on-page surface
was pure hiragana. This silently introduced obscure kanji forms the
learner never encounters in any story:

  * W00019 → `林檎` (apple) for りんご
  * W00006 → `居る` (iru, exist-animate) for いる
  * W00011 → `有る` (aru, exist-inanimate) for ある

All three are real defects: 林檎 is JLPT-out-of-scope kanji, and
居る/有る directly violate the corpus convention from the previous
section. Fix:

1. **Mint guard** in `_ensure_word` (committed): when the on-page
   `surface` has no kanji, mint with the on-page surface (for nouns/
   adj/etc.) or the kana dictionary form (for verbs). Kanji lemmas
   are only kept if the corpus actually uses kanji in that position.
2. **Regression test** `test_no_obscure_kanji_surface_in_vocab` in
   `pipeline/tests/test_referential_integrity.py`: walks every vocab
   entry's surface and asserts each kanji character appears at least
   once somewhere in the corpus (any story title or sentence).
   Failure mode and repair recipe documented in the test docstring.
3. The three legacy entries (W00006/W00011/W00019) were rewritten
   in-place to use their hiragana surfaces.

If you ever DO want to introduce an obscure-kanji form (e.g. for an
N1 advanced-vocab story), the corpus must show that kanji in actual
sentence text first; the mint guard will then keep the kanji surface
because the on-page form contains it.

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
