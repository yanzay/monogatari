# AGENTS.md — Monogatari workspace memory

Workspace-specific knowledge for future agent sessions. Concrete, factual, pointed.

---

## Project shape

Monogatari = graded-reader Japanese short-story corpus + reading-app + authoring pipeline. Stories live in `stories/story_N.json` (built artifact), authored from `pipeline/inputs/story_N.bilingual.json` (editable spec). Vocab/grammar progression in `data/vocab_state.json` and `data/grammar_state.json`. Pipeline (`pipeline/`) has deterministic validator, semantic-sanity lints, audio builder, and authoring tools at `pipeline/tools/`.

## Key files

- **`pipeline/_paths.py`** — canonical path discovery + JSON I/O. Use `from _paths import load_vocab, load_grammar, load_spec, load_story, iter_stories, parse_story_id, write_json, ROOT, STORIES, DATA, INPUTS`. Do NOT recompute `ROOT = Path(__file__)…` ad hoc.
- **`pipeline/tools/_common.py`** — re-exports above + `color()`, `iter_tokens()`, `build()`, `mint_check()`, `list_word_occurrences()`.
- **`pipeline/semantic_lint.py`** — sentence-level "is this nonsense" rules (11.1–11.10). New rules use `Issue` dataclass with `severity` ∈ {`error`, `warning`} and `location` like `"sentence 3"`.
- **`pipeline/validate.py`** — Checks 1–11 validator. `validate(story, vocab, grammar, plan=None)` → `ValidationResult` with `.valid`, `.errors`, `.warnings`. Check 11 wraps semantic_lint.
- **`pipeline/text_to_story.py::build_story(spec, vocab, grammar)`** — deterministic converter. Returns `(built_story, build_report)`.
- **`pipeline/tools/vocab.py would-mint "<JP>"`** — preview tool. Returns words a candidate sentence would silently mint. Always consult before drafting a new sentence.
- **`pipeline/regenerate_all_stories.py --story N --apply`** — only sanctioned way to rebuild a single story's `is_new` flags after a spec edit. Use `--dry-run` first.

## Vocab/grammar schema gotchas

- `vocab_state.json::words[wid]["first_story"]` is a STRING (`"story_1"`), not int. Use `parse_story_id()` to coerce. Same for `last_seen_story` and grammar `intro_in_story`.
- "Lemma" of a word = `surface` field (kanji/kana display form), NOT a separate `lemma` key. `reading` is romaji.
- Grammar state: `{"version": ..., "points": {gid: {...}}}`. `label`/`description`/`pattern` field names are inconsistently present.
- **Two parallel grammar id namespaces — bridge via `catalog_id`.** `data/grammar_state.json` keys by `G001_wa_topic` etc. `data/grammar_catalog.json` keys by `N5_wa_topic` etc. Coverage analysis MUST join via `catalog_id`. Use `pipeline/grammar_progression.coverage_status()`.
- **`grammar_state.json::points[gid]["intro_in_story"]`** is the load-bearing field for coverage tracking. `None` = not yet covered (Check 3.10/3.9, brief). `state_updater` sets it on every ship; `pipeline/tools/backfill_grammar_intros.py` repairs legacy entries.
- A bilingual spec is AUTHORITATIVE. The shipped story is derived — do NOT hand-edit.
- **Auto-tagged grammar IDs not yet in `grammar_state.json` are registered in `text_to_story.KNOWN_AUTO_GRAMMAR_DEFINITIONS`.** Some paradigm anchors (notably `G055_plain_nonpast_pair` / `N5_dictionary_form`) were never bulk-loaded. The registry carries the full state-entry definition (title/short/long/jlpt/catalog_id) so `state_updater` can attribute on first use without a hand-written plan. Three loci consult it: validator's plan (built by `step_validate` from build report's `unknown_grammar`), gauntlet's `step_coverage_floor` gid→catalog_id fallback, and `_build_state_plan`'s `new_grammar_definitions` splice. **To add a new auto-tagged paradigm anchor:** add a token-level `grammar_id` to `_classify_inflection` (or another tagger site) AND add a matching entry to `KNOWN_AUTO_GRAMMAR_DEFINITIONS`. Tests in `pipeline/tests/test_dictionary_form_attribution.py`.

## Cascade rules

Three things cascade across the corpus when you change a story:
1. **`new_words` / `new_grammar` flags** — `regenerate_all_stories.py`. Cheap.
2. **`is_new=true` token markers** — same regenerator.
3. **Audio files** — `audio/story_N/*` per-sentence. Sentence-count changes require audio rebuild for that story (bounded to one story).

Does NOT cascade automatically: **other stories' validation** when an early story removes a grammar/vocab introduction. Verify with `pytest pipeline/tests/test_validate_library.py -q` after any v1 spec edit.

## Post-ship state chain (now automatic)

`pipeline/author_loop.py author N` (live ship, no `--dry-run`) runs the complete chain:
1. Build + all gauntlet checks (validate, mint_budget, pedagogical_sanity, vocab_reinforcement, coverage_floor).
2. Write `stories/story_N.json`.
3. `state_updater` with plan auto-built from build report (mints W-IDs with full surface/kana/reading/pos/verb_class/adj_class metadata). **Hand-written plan JSON files no longer required.**
4. `regenerate_all_stories --story N --apply` to rewrite is_new flags under final word_ids.
5. `audio_builder` per-sentence and per-word MP3s (incremental).

Failure → exits non-zero with `halted_at: <step>`; `state_backups/` retains prior state. Legacy three-command dance (`regenerate → state_updater → regenerate`) is the manual recovery path only.

## Re-shipping discipline

### After failed attempt: state-backup restore

A second `state_updater` call does NOT clear attributions made by the first. If attempt 1 introduced G_A and attempt 2 introduces G_B, BOTH end up with `intro_in_story=N` in `grammar_state.json`. The dry-run will say "1 new grammar point" (G_B), but `test_grammar_introduction_cadence` will count BOTH and fail.

**Recovery:** restore `data/{vocab,grammar}_state.json` from a pre-attempt state backup in `state_backups/` BEFORE re-shipping. The backup taken immediately before the very first `state_updater` of the session is the safe restore point.

### After ID-changing re-ship: clean stale audio

`audio_builder.py` writes per-sentence audio to `audio/story_<N>/s<idx>.mp3` and per-word audio to flat `audio/words/<wid>.mp3`. If a re-ship changes word IDs (slot reuse at different position), stale `audio/words/W*.mp3` files become orphans → `test_audio_word_files_only_for_known_words` fails. Hand-delete stale files whose IDs are no longer in `data/vocab_state.json`.

### Conjunction vocab + grammar last_seen bookkeeping (since 2026-04-30)

Two pre-existing pipeline gaps fixed in one pass:

1. **Conjunctions now mint as vocab.** Surfaces in `text_to_story.CONJUNCTION_VOCAB` (だから, ですから, でも, そして, について) used to be tagged as pure grammar particles with no `word_id`, leaving the reading-app's lookup popup with nothing to resolve when the learner tapped them. They now mint **function-class** vocab records (pos=`conjunction`, _minted_by=`conjunction_registry`) on first use; the token gets BOTH `word_id` AND `grammar_id`. Function mints flow through a SEPARATE bucket — `report["new_function_words"]` — so they do NOT count against `step_mint_budget`. To add a new conjunction-class surface, add an entry to `CONJUNCTION_VOCAB` with kana/reading/pos/meanings (and optionally jlpt). Pure case-particles (は/が/を/に/から-as-source/etc.) deliberately stay wid-less. Test: `test_conjunction_surfaces_carry_word_id` in `test_state_integrity.py`. **Note for future authors:** clause-initial conjunctions NOT yet in the registry (しかし, けれども, ところが, すると, それで, だが) currently fall through to the content-word path and either mint as `<TODO>` or split incorrectly (`けれど + も`). Before using one in a story, add (a) an entry to `CONJUNCTION_VOCAB`, (b) a grammar point to `data/grammar_catalog.json` + `data/grammar_state.json`, (c) the surface→gid mapping to `SURFACE_TO_GRAMMAR`. Audit script (one-liner): `grep '<TODO>' would-mint output for any conjunction candidate`.

2. **Grammar `last_seen_story` now updates on every ship.** Previously only vocab `last_seen_story` was bumped; grammar's was never written. `state_updater.py` now has a §2b sweep that walks all story tokens (title + sentences) and sets `last_seen_story = story_id` on every `grammar_id` referenced (own field or `inflection.grammar_id`). Backfill via the corpus-walk script that landed alongside the patch — sets last_seen to the highest story_id where each gid appears. Two regression tests: `test_grammar_last_seen_story_set_for_introduced_points` and `test_grammar_last_seen_story_matches_corpus_max_use` in `test_state_integrity.py`.

State chain consequence: after this patch, `data/grammar_state.json::points[gid]["last_seen_story"]` is the load-bearing field for "when did this grammar point last appear" (mirroring vocab semantics). Reinforcement debt analysis (e.g. G009_mo_also last seen story 3, G050_he_direction last seen story 2) becomes diagnosable from state alone.

### Audio layout (since 2026-04-29)

- `audio/story_<N>/s<idx>.mp3` — per-sentence, story-scoped.
- `audio/words/<wid>.mp3` — per-word, FLAT (decoupled from story). A word can appear anywhere; tying audio to the introducing story made it undiscoverable from review/library/popups.
- Migration moved 42 files from `audio/story_<N>/w_W*.mp3` → `audio/words/W*.mp3`. Consumers updated in lockstep: `audio_builder.py` (writes `words_dir`), `test_referential_integrity.py` (orphan test), `src/lib/util/word-audio.ts::wordAudioPath`, `src/lib/data/corpus.ts::decorateWithAudioPaths`.
- Legacy `legacy/v1-audio/story_*/` left in place (v1 retired, self-contained).

## Per-story vocabulary cadence: BOTH max AND min

`mint_budget` is `{min, max, target}`. Gauntlet `mint_budget` step enforces only the max. `test_vocabulary_introduction_cadence` enforces the min (`MIN_NEW_WORDS_PER_STORY = 3` after bootstrap). Always read brief's `mint_budget.min` as a hard floor.

## text_to_story mint dedup (fixed 2026-04-29)

`_ensure_word` now keys `BuildState.minted` by `_mint_dedup_key(pos1, surface, lemma)` which returns `pos1|normalized_lemma` for inflectables (UniDic POS in {動詞, 形容詞, 形状詞, 助動詞}) and `pos1|surface` otherwise. Same verb across past/nonpast/te-form/negative in one story now counts as ONE mint.

Tests: `pipeline/tests/test_mint_dedup.py` (7 tests pinning dual-tense verb collapse, dual-form i-adj collapse, no over-dedup on distinct lemmas with same kana, lemma-empty fallback, POS-separator preventing cross-POS collisions).

## vocab_reinforcement gauntlet step is "last-slot only" (since 2026-04-29)

`_vocab_reinforcement_debt()` in `pipeline/tools/agent_brief.py` rules:
- `must_reinforce=True` ONLY when R1 window (`VOCAB_REINFORCE_WINDOW = 10`) is about to close on the word: `target_story == intro_story + VOCAB_REINFORCE_WINDOW` AND no follow-up has used it.
- Bootstrap-intro words (`intro_story <= BOOTSTRAP_END = 10`) NEVER become must_reinforce.
- Everything in-window-but-not-last-slot is `should_reinforce` (informational, non-blocking).

Post-ship test `test_vocab_words_are_reinforced` (R1) is unchanged. Authoring: 3-6 carryover words is normal; pick organic reuse.

DO NOT re-tighten without also relaxing R1 itself.

## Dry-run green ≠ corpus tests green

Gauntlet pulls some checks forward (`pedagogical_sanity`, `coverage_floor`, `mint_budget`), but corpus-wide rules only fire under `pytest pipeline/tests/`:
- `test_vocabulary_introduction_cadence` (per-story min new words)
- `test_vocab_words_are_reinforced` (per-word reinforcement window)
- `test_grammar_introduction_cadence` (per-story max new grammar)
- `test_audio_word_files_only_for_known_words` (audio orphans)

Always run `pytest pipeline/tests/ -q` after the post-ship chain.

## v1 is RETIRED

v1 corpus moved to `legacy/v1-stories/`. `V1_INCOMPATIBLE_WITH_V2_LINTS` xfail set in `test_validate_library.py` deleted. Every story in `stories/` must pass full validator (Checks 1–11) cleanly. If a v1 motif tempts you, port via `pipeline/author_loop.py author N`; do not resurrect a v1 file.

## v2 architectural commitments

Documented in `docs/v2-strategy-2026-04-27.md` and `docs/phase3-tasks-2026-04-28.md`:

- **Author = LLM agent.** No hand-authoring. Agent drafts spec, runs `author_loop.py author N`.
- **Deterministic lints are HARD BLOCK.** Validate (1–11), mint_budget, pedagogical_sanity all hard-fail. Only LLM literary reviewer is best-effort.
- **Gauntlet steps:** spec_exists → agent_brief → build → validate → mint_budget → pedagogical_sanity → literary_review (stub) → write → audio (stub). `pedagogical_sanity` pulls `test_introduced_grammar_is_reinforced` forward.
- **Brief is the agent's only memory.** Read once, fully, before drafting.
- **Override discipline:** logged soft override; same rule overridden 3× auto-suspends and escalates to human.
- **Required v2 spec fields:** `intent`, `scene_class`, `anchor_object`, per-sentence `role` ∈ {setting, action, dialogue, inflection, reflection, closer}.
- **Recurring human audit every 10 stories** (reviewer model = same family as author).
- **Per-story grammar floor (2026-04-28).** Story 4+ MUST introduce ≥1 new grammar point until current JLPT tier is fully covered. Validator Check 3.10 + gauntlet `coverage_floor` hard-block. Brief surfaces `grammar_introduction_debt`. Tier advancement (story 11 → N4) requires every prior-tier point covered (Check 3.9).

## Authoring lessons

### G055_plain_nonpast_pair (relative-clause plain-form verbs) is a cascade trap

Introducing G055 in story 4–7 fails `test_introduced_grammar_is_reinforced` because no story 4–10 currently uses plain dictionary form. Adding a downstream relative clause to story N+1 then violates `test_grammar_introduction_cadence` (max 1 after bootstrap). Spirals into 3+ story edits per attempt.

**Rule:** Do NOT introduce G055 (or any auto-tagged grammar point with no downstream usage) until at least ONE story 5–10 already organically uses the construction. **General form:** before introducing grammar G in story N, grep `stories/story_{N+1..N+5}.json` for at least one token whose `grammar_id == G`. If none, defer.

### Grammar attributions are derived, not stored (Phase A — 2026-05-01)

`intro_in_story`, `last_seen_story`, and `first_story` are no longer stored on `data/grammar_state.json::points[gid]`. They are derived from the corpus by `pipeline/derived_state.derive_grammar_attributions()` and projected for the reader by `pipeline/build_grammar_attributions.py` (writes `data/grammar_attributions.json` + `static/data/grammar_attributions.json`). The projection is rebuilt automatically by `regenerate_all_stories.py --apply`.

This eliminates an entire bug class: drift becomes mathematically impossible because the field that used to drift no longer exists. Replaces:
- the manual reconciliation runbook (deleted)
- `state_updater`'s §2-patch and §2b-sweep writes (deleted)
- `step_write`'s auto-reconcile pass (deleted)
- `pipeline/tools/reconcile_grammar_intros.py` (now a back-compat no-op)
- `test_grammar_intro_in_story_matches_corpus_first_use` and the two `test_grammar_last_seen_story_*` tests (deleted; the invariants they checked are now structural)

Two invariants pin the new contract:
- `test_grammar_state_carries_no_attribution_fields` — guards against a future state_updater regression that re-introduces the writes.
- `test_grammar_attribution_manifest_in_sync_with_corpus` — guards against the manifest going stale relative to the derivation.

**Reader app integration:** `loadGrammar()` in `src/lib/data/corpus.ts` fetches both `grammar_state.json` AND `grammar_attributions.json` in parallel and joins them, so call sites like `isSeenGrammar(gp)` keep working unchanged. A 404 on the projection falls back to "nothing introduced" (rather than crashing) so a mid-deploy doesn't break the page.

**Phase B (vocab fields — landed 2026-05-01):** `first_story`, `last_seen_story`, and `occurrences` per word got the same treatment. Same architecture: `derived_state.derive_vocab_attributions()` is the single source of truth; `build_vocab_attributions.py` writes the manifest at `data/vocab_attributions.json` + `static/data/vocab_attributions.json`; `loadVocabIndex()` in `corpus.ts` joins it onto each word + index row at fetch time. The pre-Phase-B `occurrences` field was systematically drifting LOW by 1-15+ per word (e.g. 母 stored as 6, actually 19) — that bug is now mathematically impossible. State_updater no longer writes any of the three fields; brand-new word records carry definition metadata only. Pinned by `test_vocab_state_carries_no_attribution_fields` and `test_vocab_attribution_manifest_in_sync_with_corpus`. Pipeline read-side ergonomics: `_paths.load_vocab_attributed()` overlays the derivation onto a fresh `vocab_state.json` read so existing read sites need only swap their loader (palette, agent_brief, lookup, vocab CLI, build_vocab_shards). State-write sites (state_updater, text_to_story) keep raw `load_vocab()`.

### Closer cliché ladder needs ongoing curation

Fresh patterns become clichés after 2–3 stories. Sub-templates emerging:
- `Nは[i-adj]です` as closer (stories 3, 7) → ban next i-adj-attribute closer.
- Departure-walks (story 4) → ban for stories 5–9.
- Listing-と reflection (`N₁とN₂は…です`) → variants OK; same-shape repeats banned.

**Rule:** scan previous 3 stories' closers for SHAPE (subject-particle-attribute-copula, possessive-departure-verb, listing-equivalence). Match shape = rotate.

### Re-ship cleanup chain (failed attempt with mints + grammar)

1. Restore `data/{vocab,grammar}_state.json` from pre-attempt backup in `state_backups/` or `/tmp/`.
2. Hand-delete stale `audio/story_N/w_W*.mp3` for IDs no longer in vocab_state.
3. Hand-delete stale `audio/story_N/sX.mp3` where X exceeds new sentence count.
4. Re-ship the revised story (`author_loop.py author N` — reconciliation now happens automatically inside `step_write`; no manual reconciliation script needed).
5. `audio_builder.py` for stories whose sentence text changed.
6. Full pytest sweep.

### Orthographic consistency: hiragana for grammaticalized verbs

For grammaticalized existence verbs (ある, いる, なる, できる, etc.), use HIRAGANA. Stories 9 and 10 originally used `有ります`; corrected with:

```bash
sed -i.tmp 's/有ります/あります/g' pipeline/inputs/story_*.bilingual.json
rm pipeline/inputs/*.tmp
```

Then regen + audio rebuild.

### No-obscure-kanji mint guard (since 2026-04-29 evening)

Minted vocab `surface` field is what the learner sees. `_ensure_word` previously used UniDic *lemma* (which prefers kanji canonical forms) even when on-page surface was hiragana. Defects: W00019→`林檎`, W00006→`居る`, W00011→`有る`.

**Mint guard:** when on-page `surface` has no kanji, mint with on-page surface (nouns/adj) or kana dictionary form (verbs). Kanji lemmas only kept if corpus actually uses kanji.

**Regression test:** `test_no_obscure_kanji_surface_in_vocab` in `pipeline/tests/test_referential_integrity.py`. Walks vocab surfaces; each kanji must appear ≥1 in some story.

To introduce an obscure-kanji form intentionally, use it in actual sentence text first; the guard then keeps the kanji surface.

### Lexical difficulty cap (since 2026-04-29 evening)

Per-story JLPT+nf-band cap on newly-minted vocab:

```
Story 1–10  (bootstrap) → max JLPT N5, max nf06 (~rank 3,000)
Story 11–25             → max JLPT N4, max nf12 (~rank 6,000)
Story 26–50             → max JLPT N3, max nf24 (~rank 12,000)
Story 51+               → max JLPT N2, max nf48 (any)
```

Word PASSES if it satisfies EITHER signal. No-JLPT but `ichi1` tag (Ichimango basic-vocab) is rescued — catches Tanos gaps like りんご, バナナ, かばん.

**Data:** `data/jlpt_vocab.json` (~280KB; sourced from stephenmk/yomitan-jlpt-vocab). Hardlinked to `static/data/jlpt_vocab.json`. Levels are ints 5..1 (5=N5). Four lookup keys:
- `by_jmdict_seq[seq]` → level (best for disambiguation)
- `by_kanji_kana["kanji|kana"]` → level (canonical when both known)
- `by_kanji[kanji]` → lowest-level (loose; collides on homographs)
- `by_kana[kana]` → lowest-level (loose)

`pipeline/lexical_difficulty.py` lookup uses specific keys first, falls back to loose.

**Three integration points:**
1. **Mint enrichment** (`text_to_story.py::_ensure_word`): every new vocab gets `jlpt`, `nf_band`, `common_tags` cached at mint time. Failure-tolerant.
2. **Agent brief** (`agent_brief.py::_lexical_difficulty_constraints`): surfaces cap + override discipline + existing above-cap palette words. In `hard_limits.lexical_difficulty_cap`.
3. **Gauntlet step** (`author_loop.py::step_vocab_difficulty`): inspects newly-minted words; HARD-FAILS if any exceed cap and aren't absorbed by `lexical_overrides`.

**Override discipline:** spec MAY declare `lexical_overrides: ["surface", ...]` to absorb up to **MAX_OVERRIDES_PER_STORY=2** above-cap mints per story (raised from 1 → 2 on 2026-04-29 — bootstrap stories often need a domain where the second above-cap mint is scene-grounding). Override must be acknowledged in `spec.intent`. ≥3 overrides → split the scene.

**Backfilled legacy entries:**
- W00026 袋 (story 2, N3) → `lexical_overrides=["袋"]`.
- W00029 皿 + W00030 包丁 (story 3, N3 + N2) → `lexical_overrides=["皿","包丁"]` (instrument anchor for G017_de_means; ナイフ is wrong — means table/penknife in JP).

After backfill: `step_vocab_difficulty` is HARD-BLOCK; `test_no_above_tier_vocab_without_override` runs without xfail.

## Naturalness defects (corrected 2026-04-30)

Surface-level lexical/idiomatic concerns the validator cannot model. The §E.7.5 native-naturalness subagent (in SKILL.md) is the prospective gate. **Run §E.7.5 before EVERY ship.**

Defect patterns:

- **持つ overloaded as take/receive/remove**: 持つ = "hold/carry as ongoing state" only. Past 持ちました reads as "began carrying briefly," not "took." Use 取る (pick up — N5), 受け取る (receive — N3), 出す (take out — N5).
- **Size-on-mass-noun (小さい/大きい on liquids/foods)**: 小さいお茶 not natural — お茶 is mass; size the container (お茶碗) not the tea. Same for 大きいパン (borderline).
- **Pedagogically-redundant particles**: 「お金で買います」 — buying always implies money; お金で is empty pedagogy. Use で-means via verb where means is genuinely informative (包丁で切ります).
- **Bare 持ちません vs 持っていません for state-change**: "no longer holding" is state-change → te-iru + ません. Bare 持ちません = habitual non-past.
- **Bare quoted 「…」 with no 言う/呼ぶ framing**: reads as stage direction, not prose.
- **Wrong location particles for stative verbs**: で = activity-location; に = state-location. 「私の前で傘を持っています」 wrongly uses で; correct: 「私の前に立って、傘を持っています」.
- **歩く vs 行く for room-to-room movement**: 歩く foregrounds manner; 行く is neutral "go to." Inside a house, prefer 行く.
- **見る on people in greeting context**: 「私は母を見ます」 reads clinical. Use 母に会う or flip to 「母は私を見ます」.

## Full state reset vs in-place spec edit

For corpus-wide rewrites that change vocab introduction order, full reset is operationally cheaper than patching state in-place. Reset script:

```bash
mkdir -p /tmp/monogatari_pre_reset
cp data/vocab_state.json /tmp/monogatari_pre_reset/
cp data/grammar_state.json /tmp/monogatari_pre_reset/
cp -r stories audio /tmp/monogatari_pre_reset/

python3 -c "
import json
v = json.load(open('data/vocab_state.json'))
g = json.load(open('data/grammar_state.json'))
v['words'] = {}
v['next_word_id'] = 'W00001'
v['last_story_id'] = None
for p in g['points'].values():
    p['intro_in_story'] = None
    p['last_seen_story'] = None
g['last_story_id'] = None
json.dump(v, open('data/vocab_state.json','w'), indent=2, ensure_ascii=False)
json.dump(g, open('data/grammar_state.json','w'), indent=2, ensure_ascii=False)
"

rm -rf stories/* audio/story_* audio/words/W*.mp3

for n in 1 2 3 4 5; do
  python3 pipeline/author_loop.py author $n
done
```

The 2026-04-30 corpus rewrite of stories 1–5 used this path. Final state: 36 vocab words, 20 grammar points, 147 tests passing.

## Shell quirks

- `cd pipeline/tools && python3 ...` sometimes fails (CWD doesn't persist). **Always invoke scripts with full path from project root**: `python3 pipeline/tools/palette.py ...` (no cd).
- Project uses `.venv/`. Always prepend `source .venv/bin/activate &&` for fugashi/jaconv/jamdict imports. Bare `/opt/homebrew/.../python3.14` will fail with "fugashi/jaconv/jamdict are required."

## Standing user preferences

### Auto-commit and push after a clean ship (permanent, since 2026-04-28)

User instruction: "commit and push, do not ask ever again." For any clean ship (gauntlet `VERDICT: ship`, full pytest green, §E.5/E.6/E.7/E.7.5 pass), proceed directly to `git add … && git commit … && git push` WITHOUT asking. Default-confirm-on-write is overridden for git in this workspace.

### "Rewrite story N and run tests, then restore"

Take backups to `/tmp/` BEFORE editing, do the work, restore from backups, re-verify tests at the end:

```bash
cp pipeline/inputs/story_N.bilingual.json /tmp/story_N.bilingual.json.bak
cp stories/story_N.json /tmp/story_N.json.bak
# work
cp /tmp/story_N.bilingual.json.bak pipeline/inputs/story_N.bilingual.json
cp /tmp/story_N.json.bak stories/story_N.json
python3 -m pytest pipeline/tests/ -q
```

### When the user vents about quality

(1) Acknowledge frustration honestly without fawning. (2) Gather evidence before promising a plan. (3) Propose something **bounded** (not "rebuild from scratch"). (4) Flag implications of seemingly-reasonable choices ("default retire" + "best-effort + warn" together = hidden quality regression).

## Patterns

### Parallel subagents for "read N stories with same rubric"

Three subagents reading 19 stories each in parallel beat one agent reading 56 sequentially. Rubric convergence across independent agents is itself signal. Use for any "survey the whole corpus / repo / dataset" task.

### Conservatism in lint design is intentional

`semantic_lint.py`'s `INANIMATE_QUIET_NOUN_IDS` deliberately EXCLUDES 雨/月/星/空/風 (natural JP pathetic-fallacy). Respect existing exclusion lists and module-level docstrings — they encode native-speaker calls overruling audit findings.

### Existing tooling is comprehensive

`pipeline/tools/` + `pipeline/lookup.py` cover ~80% of authoring-support needs. Inventory existing tools (`ls pipeline/tools/ && head pipeline/lookup.py`) before proposing new ones.

### `would-mint` is the right preflight

Avoid the multi-iteration "draft → tokenize → discover unknown word → rewrite" loop. Each iteration ≈ 3 wasted tool calls.
