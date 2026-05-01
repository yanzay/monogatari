"""Regression tests for plain dictionary-form (N5_dictionary_form) attribution.

Background — the bug this guards against:

  Until 2026-04-28, a verb in plain dictionary form (e.g. 「私は月を見る。」)
  was tagged with NO grammar_id by `text_to_story.merged_to_token_json`.
  As a consequence:
    * The validator's Check 3.10 ("must introduce ≥1 new grammar point
      per post-bootstrap story") never saw N5_dictionary_form even when
      the agent deliberately ended a sentence in plain form to land it.
    * The recommender (`pipeline/grammar_progression.rank_uncovered`)
      would happily recommend `N5_dictionary_form` to the agent, the
      agent would write a plain-form closer, and the gauntlet would
      report "0 new grammar points." The agent had no honest way to
      land the catalog entry.

  The fix wires `_classify_inflection` to return
  `N5_dictionary_form` for pure dictionary form, and adds a
  `KNOWN_AUTO_GRAMMAR_DEFINITIONS` registry consulted by
  `author_loop._build_state_plan` so the first plain-form usage in
  the corpus can be attributed by `state_updater` cleanly.

These tests pin both halves of the fix.
"""
from __future__ import annotations

import json

import pytest

from text_to_story import (  # noqa: E402
    KNOWN_AUTO_GRAMMAR_DEFINITIONS,
    build_story,
)


PLAIN_NONPAST_GID = "N5_dictionary_form"


def _build(spec_sentences: list[dict], vocab: dict, grammar: dict) -> tuple[dict, dict]:
    spec = {
        "story_id": 999,
        "title": {"jp": "テスト", "en": "Test"},
        "sentences": spec_sentences,
    }
    return build_story(spec, vocab, grammar)


def _verb_token(built: dict, surface: str) -> dict | None:
    for sec in built.get("sentences", []):
        for tok in sec.get("tokens", []):
            if tok.get("t") == surface and tok.get("role") == "content":
                return tok
    return None


def test_honorific_prefix_merges_into_single_noun(vocab, grammar):
    """Phase 4.1 (2026-04-29): UniDic tokenizes honorific-prefix nouns
    as TWO tokens (接頭辞 御/お,ご + 名詞). text_to_story::merge_tokens
    Rule 0a glues them into a single content token whose surface and
    lemma are the concatenation (お茶 / お金 / ご家族 / お土産).

    Without this rule, the prefix becomes a stranded <TODO> in the
    build report and the noun gets minted as a separate W-id (e.g. 茶
    alone instead of お茶) — pedagogically wrong because every textbook
    treats the prefixed form as the canonical learner-facing lemma.

    Lexicalized prefix-noun compounds (e.g. ご飯 → 御飯) are tokenized
    as a single 名詞 by UniDic and don't enter the merge branch; this
    test only covers the productive-prefix path.
    """
    samples = [
        ("お茶があります。",       "お茶",   "おちゃ"),
        ("お皿は小さいです。",     "お皿",   "おさら"),
        ("お金で買います。",       "お金",   "おかね"),
        ("ご家族と話します。",     "ご家族", "ごかぞく"),
    ]
    for jp, expected_surface, expected_kana in samples:
        built, report = _build([{"jp": jp, "en": ""}], vocab, grammar)
        content = [
            t for t in built["sentences"][0]["tokens"]
            if t.get("role") == "content"
        ]
        # The honorific noun must be the FIRST content token and a
        # single token (not split into two: お + 茶).
        assert content, f"no content tokens for {jp!r}"
        first = content[0]
        assert first["t"] == expected_surface, (
            f"{jp!r}: expected first content token surface {expected_surface!r}, "
            f"got {first['t']!r} — honorific-prefix merge regressed"
        )
        # Reading must include the prefix kana.
        assert first.get("r") == expected_kana, (
            f"{jp!r}: expected reading {expected_kana!r}, "
            f"got {first.get('r')!r}"
        )
        # No <TODO> stranded prefix anywhere in the build report.
        unresolved_surfaces = [
            (u.get("surface") if isinstance(u, dict) else u)
            for u in (report.get("unresolved") or [])
        ]
        assert "お" not in unresolved_surfaces and "ご" not in unresolved_surfaces, (
            f"{jp!r}: stranded honorific prefix in unresolved: "
            f"{unresolved_surfaces}"
        )


def test_plain_form_of_polite_vocab_tags_g055(vocab, grammar):
    """見る (plain form of polite-form vocab 見ます) must carry
    grammar_id N5_dictionary_form AND inflection.form='plain_nonpast'.

    Self-seeding: this test used to depend on the live vocab state
    containing 見ます (W00010 in the v2.0 corpus). After the v2.5
    reload (2026-04-29) the corpus starts empty, so we mint a local
    copy of the vocab with 見ます manually inserted under the
    test-only id WTEST10. The grammar_id attribution path is what's
    under test; the W-id is incidental.
    """
    vocab = json.loads(json.dumps(vocab))  # deep copy — don't mutate fixture
    # The test exercises the "polite-form-vocab seen in plain form"
    # path. We need 見ます (polite) in vocab AND we need 見る (plain)
    # to NOT be a separate vocab entry — otherwise the resolver
    # short-circuits to the plain entry and never enters the
    # polite-pair path. Drop any pre-existing 見る entry from the
    # copy, then mint 見ます under a high-numbered test-only id.
    for wid in list(vocab.get("words", {})):
        if vocab["words"][wid].get("surface") == "見る":
            del vocab["words"][wid]
    vocab.setdefault("words", {})["W99910"] = {
        "id":          "W99910",
        "surface":     "見ます",
        "kana":        "みます",
        "reading":     "mimasu",
        "pos":         "verb",
        "verb_class":  "ichidan",
        "meanings":    ["see", "look"],
        "occurrences": 1,
        "first_story": "story_1",
    }
    built, _ = _build(
        [{"jp": "私は月を見る。", "en": "I see the moon."}],
        vocab, grammar,
    )
    tok = _verb_token(built, "見る")
    assert tok is not None, "expected a content token for 見る"
    assert tok.get("grammar_id") == PLAIN_NONPAST_GID, (
        f"plain form of 見ます should carry {PLAIN_NONPAST_GID}, "
        f"got {tok.get('grammar_id')}"
    )
    infl = tok.get("inflection") or {}
    assert infl.get("form") == "plain_nonpast", (
        f"plain-form-of-polite-vocab path should rename form to "
        f"'plain_nonpast' (got {infl.get('form')})"
    )


def test_pure_dictionary_form_vocab_tags_g055(vocab, grammar):
    """取る (vocab record IS already the dict form) must carry
    grammar_id N5_dictionary_form AND inflection.form='dictionary'.
    """
    built, _ = _build(
        [{"jp": "私は手紙を取る。", "en": "I take the letter."}],
        vocab, grammar,
    )
    tok = _verb_token(built, "取る")
    assert tok is not None, "expected a content token for 取る"
    assert tok.get("grammar_id") == PLAIN_NONPAST_GID
    infl = tok.get("inflection") or {}
    assert infl.get("form") == "dictionary", (
        f"pure dict-form vocab should keep form='dictionary' "
        f"(got {infl.get('form')})"
    )


def test_polite_form_does_not_tag_g055(vocab, grammar):
    """見ます (polite) must keep N5_masu_nonpast — no regression."""
    built, _ = _build(
        [{"jp": "私は月を見ます。", "en": "I see the moon."}],
        vocab, grammar,
    )
    tok = _verb_token(built, "見ます")
    assert tok is not None, "expected a content token for 見ます"
    assert tok.get("grammar_id") == "N5_masu_nonpast", (
        f"polite form should remain N5_masu_nonpast, got {tok.get('grammar_id')}"
    )
    assert tok.get("grammar_id") != PLAIN_NONPAST_GID


def test_te_form_does_not_tag_g055(vocab, grammar):
    """取って (te-form) must remain N5_te_form — the dict-form fix
    must not bleed into other inflections.
    """
    built, _ = _build(
        [{"jp": "私は手紙を取って、椅子に座ります。",
          "en": "I take the letter and sit on the chair."}],
        vocab, grammar,
    )
    tok = _verb_token(built, "取って")
    assert tok is not None
    assert tok.get("grammar_id") == "N5_te_form"


def test_unknown_grammar_report_includes_g055_when_unattributed(vocab, grammar):
    """When G055 is not yet attributed in grammar_state, the build
    report should surface it in `unknown_grammar` so the planner can
    splice in the registry definition.
    """
    if "N5_dictionary_form" in (grammar.get("points") or {}):
        pytest.skip("G055 already attributed — corpus is past first dict-form usage.")
    _, report = _build(
        [{"jp": "私は月を見る。", "en": "I see the moon."}],
        vocab, grammar,
    )
    surfaced = {
        rec["grammar_id"]
        for rec in report.get("unknown_grammar", []) or []
        if isinstance(rec, dict) and rec.get("grammar_id")
    }
    assert PLAIN_NONPAST_GID in surfaced, (
        f"build report should surface {PLAIN_NONPAST_GID} as unknown_grammar "
        f"so the planner can attribute it (got: {sorted(surfaced)})"
    )


def test_known_auto_grammar_definitions_registry_is_complete():
    """The G055 entry in the registry must carry every field
    state_updater requires for a brand-new grammar point (case A in
    state_updater.update_state).
    """
    defn = KNOWN_AUTO_GRAMMAR_DEFINITIONS.get(PLAIN_NONPAST_GID)
    assert defn is not None, (
        f"{PLAIN_NONPAST_GID} must be in KNOWN_AUTO_GRAMMAR_DEFINITIONS"
    )
    # Required (state_updater raises if any of these are missing):
    for field in ("title", "short", "long"):
        assert defn.get(field) and isinstance(defn[field], str), (
            f"{PLAIN_NONPAST_GID}.{field} must be a non-empty string"
        )
    # Pinning catalog_id is the load-bearing field for coverage tracking
    # (grammar_progression.coverage_status joins state ↔ catalog by
    # catalog_id). If this drifts off N5_dictionary_form, the brief's
    # recommender will keep recommending the catalog point even after
    # the first plain-form usage shipped.
    assert defn.get("catalog_id") == "N5_dictionary_form"
    assert defn.get("jlpt") == "N5"


def test_step_coverage_floor_counts_g055_via_registry(vocab, grammar, tmp_path, monkeypatch):
    """step_coverage_floor must consult KNOWN_AUTO_GRAMMAR_DEFINITIONS so a
    plain-form-verb story (post-bootstrap, current tier uncovered) lands
    its intro in the count even when G055 isn't yet in grammar_state.

    This pins the second half of the fix: without the registry fallback in
    step_coverage_floor's gid→catalog_id map, a plain-dict closer would
    pass the validator's Check 3.10 (which uses a permissive
    "gp.get('intro_in_story') is None" check) but FAIL the gauntlet's
    coverage_floor (which used a stricter "gid must be in state" lookup).
    """
    if "N5_dictionary_form" in (grammar.get("points") or {}):
        pytest.skip("G055 already attributed — registry path no longer fires.")

    from author_loop import step_coverage_floor  # noqa: E402

    built, _ = _build(
        [
            {"jp": "夜、月は明るいです。", "en": "Night, the moon is bright."},
            {"jp": "私は月を見る。", "en": "I see the moon."},
        ],
        vocab, grammar,
    )

    # Pick a post-bootstrap story id (BOOTSTRAP_END is 3); at the current
    # corpus state N5 still has uncovered points so the floor applies.
    res = step_coverage_floor(11, built)
    assert res.status == "ok", (
        f"plain-dict closer should satisfy coverage_floor via the registry "
        f"fallback; got status={res.status}, summary={res.summary!r}"
    )
    intros = (res.details or {}).get("intros") or []
    assert PLAIN_NONPAST_GID in intros, (
        f"coverage_floor should count {PLAIN_NONPAST_GID} as an intro "
        f"(got intros={intros})"
    )


def test_validator_accepts_g055_via_unknown_grammar_splice(vocab, grammar):
    """Validator Check 3 ("grammar_id X not in grammar_state or plan") must
    NOT block a story that uses a plain-form verb when the gauntlet's
    step_validate splices `unknown_grammar` records into the plan.

    This pins the third half of the fix: without the splice, the very
    first plain-dict story in the corpus would emit
    `grammar_id 'N5_dictionary_form' not in grammar_state or plan`
    and the gauntlet would halt at validate.
    """
    if "N5_dictionary_form" in (grammar.get("points") or {}):
        pytest.skip("G055 already attributed — splice path no longer needed.")

    from validate import validate as run_validate  # noqa: E402

    built, report = _build(
        [{"jp": "私は月を見る。", "en": "I see the moon."}],
        vocab, grammar,
    )

    # Without splicing G055, validator Check 3 raises.
    res_no_plan = run_validate(built, vocab, grammar, plan=None)
    check3_errors = [
        e for e in res_no_plan.errors
        if str(e.check) == "3" and PLAIN_NONPAST_GID in e.message
    ]
    assert check3_errors, (
        "expected validator to flag G055 as unknown without a plan splice"
    )

    # WITH splicing — replicates step_validate's logic.
    minted_grammar = []
    for rec in (report.get("unknown_grammar") or []):
        if isinstance(rec, dict):
            g = rec.get("grammar_id")
            if g and g not in minted_grammar:
                minted_grammar.append(g)
    plan = {"new_words": [], "new_grammar": minted_grammar}
    res_with_plan = run_validate(built, vocab, grammar, plan=plan)
    check3_after = [
        e for e in res_with_plan.errors
        if str(e.check) == "3" and PLAIN_NONPAST_GID in e.message
    ]
    assert not check3_after, (
        f"after splicing {PLAIN_NONPAST_GID} into plan.new_grammar, "
        f"validator Check 3 should not fire on it; got: {check3_after}"
    )


def test_build_state_plan_splices_g055_definition(vocab, grammar):
    """The author_loop helper must read G055 out of the build report's
    unknown_grammar list and splice the registry definition into the
    plan, so state_updater's "case (a)" branch (brand-new gid) can
    proceed without raising "Cannot ship: new_grammar 'G055_…' has
    no complete definition in plan."
    """
    if "N5_dictionary_form" in (grammar.get("points") or {}):
        pytest.skip("G055 already attributed — registry path no longer fires.")
    from author_loop import _build_state_plan  # noqa: E402

    _, report = _build(
        [{"jp": "私は月を見る。", "en": "I see the moon."}],
        vocab, grammar,
    )
    plan = _build_state_plan(report)
    grammar_defs = plan.get("new_grammar_definitions") or {}
    assert PLAIN_NONPAST_GID in grammar_defs, (
        f"_build_state_plan must populate new_grammar_definitions["
        f"'{PLAIN_NONPAST_GID}'] from KNOWN_AUTO_GRAMMAR_DEFINITIONS "
        f"(got: {sorted(grammar_defs.keys())})"
    )
    spliced = grammar_defs[PLAIN_NONPAST_GID]
    # state_updater requires title/short/long to be present + truthy.
    assert spliced.get("title") and spliced.get("short") and spliced.get("long")
    assert spliced.get("catalog_id") == "N5_dictionary_form"
