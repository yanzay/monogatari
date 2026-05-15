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


def _build(spec_sentences: list[dict], vocab: dict, grammar: dict, *, new_word_meanings: dict | None = None) -> tuple[dict, dict]:
    spec = {
        "story_id": 999,
        "title": {"jp": "テスト", "en": "Test"},
        "sentences": spec_sentences,
    }
    if new_word_meanings:
        spec["new_word_meanings"] = new_word_meanings
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
    # Provide explicit meanings so the post-Flaw-#5 fail-loud mint path
    # doesn't error on words jamdict can't gloss (e.g. ご家族, お皿).
    # The honorific-merge logic under test is unaffected by the meaning
    # field; we just need _ensure_word to not abort.
    spec_meanings = {
        "お茶": "tea (polite)",
        "お皿": "plate (polite)",
        "お金": "money (polite)",
        "ご家族": "family (honorific)",
    }
    for jp, expected_surface, expected_kana in samples:
        built, report = _build(
            [{"jp": jp, "en": ""}],
            vocab, grammar,
            new_word_meanings=spec_meanings,
        )
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


# NOTE (removed 2026-05-15): four bootstrap-fallback tests used to live
# below this line — they exercised the one-shot path that fired when
# `N5_dictionary_form` was minted into grammar_state for the very first
# plain-dict story in the corpus (story 7). They each guarded their body
# with `if "N5_dictionary_form" in grammar.get("points"): pytest.skip(...)`,
# which is now permanently true and will never flip back. The removed
# tests were:
#   - test_unknown_grammar_report_includes_g055_when_unattributed
#   - test_step_coverage_floor_counts_g055_via_registry
#   - test_validator_accepts_g055_via_unknown_grammar_splice
#   - test_build_state_plan_splices_g055_definition
#
# The steady-state behavior they covered is still pinned by the surviving
# tests in this module (test_plain_form_of_polite_vocab_tags_g055,
# test_pure_dictionary_form_vocab_tags_g055, test_polite_form_does_not_tag_g055,
# test_te_form_does_not_tag_g055, test_known_auto_grammar_definitions_registry_is_complete).
# Recover from git history (commit prior to this removal) if a future
# bootstrap-style fallback path is ever reintroduced.
