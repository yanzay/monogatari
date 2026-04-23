# Library Quality Plan — Re-enabling Skipped Tests

> Status: Phase 1 in progress. Update this document as phases land.

## Goal

Enable every currently-skipped pedagogical test and validator check
(`PEDAGOGICAL_CADENCE_ENABLED`, `test_check14_*`) **without** weakening
the rules. Improve the library by editing prose, weaving grammar/vocab
across stories, and only adjusting thresholds with written justification
when the rule itself is wrong.

## Inventory of skipped checks (snapshot 2026-04-24)

| ID | Test/Check | Enforces | Violations on enable |
|----|---|---|---|
| A | `test_grammar_introduction_cadence` (Rule A max 1/story; Rule B ≥1/5-window) | No cramming AND no stagnation | 23 |
| B | `test_vocabulary_introduction_cadence` (≥3 new words/story) | Library keeps growing | 2 (story_4, story_40) |
| C | `test_introduced_grammar_is_reinforced` (≥1 use in next 5 stories) | New grammar lands | 12 |
| D | `test_vocab_words_are_reinforced` (≥2 uses in next 10 stories) | New vocab lands | ~37 |
| E | `test_no_vocab_word_abandoned` (max 20-story gap) | SRS continues | 2 (W00112, W00215) |
| F | Validator Check 3.6 (cadence) | Same as A, per-story gate | gated off |
| G | Validator Check 3.7 (vocab floor) | Same as B, per-story gate | gated off |
| H | Validator Check 3.8 (reinforcement) | Same as C, per-story gate | gated off |
| I | `test_check14_fires_when_title_equals_grammar_surface` | Anti-spoiler guardrail | self-skips (no `surfaces` field in catalog) |

## Phases

### Phase 1 — Honest data first ✅ COMPLETE (no changes)

Investigated whether "cramming" violations were tagging bugs. **None
were.** Findings:

| Suspect | Verdict |
|---|---|
| story_32 (ね / と言います / か) | All three genuine firsts. Stories 1-31 are entirely declarative — no question-か anywhere. |
| story_45 (何 / i-adj-past) | Both genuine firsts. |
| story_6 (G021 ある/いる + G004 に_location) | Genuine. Earlier 「います」 was te-iru aux (G008), not existence; earlier 「に」 was time/te-iru, not locative. |
| story_8 (counters + で_means) | Both genuine firsts. |
| story_13 (だ + とき) | Both genuine firsts. |
| Bootstrap 13 vs cap 11 | Story_1's 9 intros are the irreducible reader-bootstrap set (は/が/を/です/ます/て-form/て-いる/i-adj/から). |

**Conclusion:** All cited "cramming" reflects real authoring choices,
not tagging artifacts. Subsequent phases must do the real work: weave
reinforcement, smooth cadence, justify the bootstrap cap.

### Phase 2 — Grammar reinforcement weaving ✅ COMPLETE

All 12 reinforcement gaps closed. `test_introduced_grammar_is_reinforced`
now passes (0 violations, was 12).

Per-weave summary:

| Gid | Intro | Wove into | New sentence |
|---|---|---|---|
| G016_na_adjective | 3 | 4 | 「静かな公園です。」(replaced existing predicate-な) |
| G025_counters | 8 | 9 | 「猫と私、二人で朝です。」(also covers G017_de_means) |
| G017_de_means | 8 | 9 | (covered by 二人で in G025 weave) |
| G024_da | 13 | 15 | 「歩くとき、『夜は静かだ』と思います。」 |
| G018_toki_when | 13 | 15 | (covered by とき in G024 weave) |
| G019_te_oku | 14 | 16 | 「パンを食べておきます。」 |
| G034_ne_confirm | 32 | 33 | 「祖母は『大切ですね』と言います。」 |
| G037_ka_question | 32 | 33 | 「『古い時計ですか』と私は言います。」 |
| G035_arimasen | 43 | 44 (auto) | bug fix — G035 was being overridden by G021 in the regen post-pass |
| G045_nan_what | 45 | 46 | 「春は何ですか。」 |
| G047_i_adj_past | 45 | 46 | 「冬の朝は寒かったです。」 |
| G056_plain_past_pair | 64 | 66 | 「『人が来た。何も言わなかった』と書きます。」 |

Side effects (all positive):

- Removed orphan word 雑誌 (W00209) from story_66 — was a
  one-shot abandoned vocab.
- Bug fix in `pipeline/regenerate_all_stories.py`: the post-pass
  override of ある/いる → G021 was clobbering the more specific
  G035_arimasen; now only overrides when current gid is None or
  the generic G026_masu_nonpast.
- Added auto-cleanup of orphan vocab records in the regenerator
  (drops vocab entries no longer referenced by any shipped story).

Token-band fixes required:

- Story_16 (intro 二人で moved its content count to 35; band [16,34]).
  Compressed sentence 7 by removing 一緒に.
- Story_66 (added a 14th sentence pushed it to 76 tokens; band [34,74]).
  Removed sentence 14 (「私は雑誌がほしいです」) which was tangential
  and contained the now-orphan 雑誌.

### Phase 3 — Vocab early-reinforcement weaving

37 violations. Batch by semantic field; weave 1-2 sentence edits per
cluster. Persistently un-reusable words → record in
`KNOWN_VOCAB_REINFORCEMENT_DEBT` (mirroring existing
`KNOWN_REINFORCEMENT_DEBT`).

### Phase 4 — Vocab abandonment

W00112, W00215 — keep + reinforce in story 60+, OR delete from vocab if
they were minted incorrectly.

### Phase 5 — Vocab floor

story_4 (2 → 3+ new words), story_40 (2 → 3+ new words). Trivial.

### Phase 6 — Cadence smoothing (Check A)

- Bootstrap cap 11 → 13 (justified: irreducible foundational set), OR
  re-shape stories 1-3.
- Per-story 2-3 intros (stories 6/8/13/32/45): if Phase 1 doesn't dissolve
  these, push intros to earlier stories where the surface naturally fits.
- 15..30 stagnation: introduce 3 modest grammar points across stories
  16/22/28 (candidates: G030 から_reason, G041 ませんか, G049 が_but).

### Phase 7 — Re-enable Check 14

Populate `surfaces` field in `data/grammar_catalog.json` for 10-15
short, unambiguous grammar points (て-form, masen, polite-past, etc.).
Removes the test's self-skip and gives the anti-spoiler check teeth.

### Phase 8 — Flip the flags

Set `PEDAGOGICAL_CADENCE_ENABLED = True` in both `pipeline/validate.py`
and `pipeline/tests/test_pedagogical_sanity.py`. Final pytest run must
be green except deferred audio.

### Phase 9 — Audio (deferred)

Regenerate sentence MP3s for stories whose prose changed during Phases
2-6. Out of scope unless explicitly requested.

## Risk register

- Reweaving regresses gloss-ratio (Check 9) → re-validate after each edit
- Adding tokens pushes out of token-band (Check 7) → prefer compact phrasings
- Library-wide first-occurrence shifts after edits → regenerator is
  idempotent; flags settle on a second `--apply`
- Large diffs → one commit per phase, descriptive messages

## Conventions

- Bilingual specs in `pipeline/inputs/*.bilingual.json` are the only
  thing edited. `stories/*.json` is regenerated.
- Every phase ends with: `regenerate_all_stories.py --apply` →
  `validate.py` for affected stories → `pytest` → commit.
- Threshold changes require a written justification comment in
  `pipeline/grammar_progression.py`.
