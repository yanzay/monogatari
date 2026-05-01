"""Unit tests for individual semantic_lint rules.

Each rule should:
  1. Fire on the canonical defect that motivated it.
  2. NOT fire on the canonical false-positive that the rule design had to
     work around.

Both directions matter equally — a rule that catches the bug but also
fires on good prose teaches authors to ignore the lint.

Added 2026-04-22 (v0.14) alongside the location-を-with-noun-list rule
and the W00018 / W00021 inanimate-quiet id-vs-comment fix.
"""
from __future__ import annotations

import pytest

from pipeline.semantic_lint import semantic_sanity_lint


def _wrap(tokens, idx=0):
    """Helper: wrap a token list in the minimal story-shaped dict."""
    return {"sentences": [{"idx": idx, "tokens": tokens}]}


# ── Rule 11.1: inanimate-thing-is-quiet ───────────────────────────────────────

def test_inanimate_quiet_fires_on_book_is_quiet():
    """Canonical defect from the 2026-04-22 audit: 本は静かです."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "本", "word_id": "W00033", "role": "content"},
        {"t": "は", "grammar_id": "N5_wa_topic", "role": "particle"},
        {"t": "静か", "word_id": "W00011", "role": "content"},
        {"t": "です", "grammar_id": "N5_desu", "role": "aux"},
        {"t": "。", "role": "punct"},
    ]))
    assert any("Inanimate" in i.message and "本" in i.message for i in issues)


def test_inanimate_quiet_does_NOT_fire_on_evening_is_quiet():
    """夕方は静かです is perfectly natural JP. The original list mistakenly
    contained W00018 (夕方) under the comment '卵'; v0.14 substituted in
    the real 卵 id (W00021)."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "夕方", "word_id": "W00018", "role": "content"},
        {"t": "は", "grammar_id": "N5_wa_topic", "role": "particle"},
        {"t": "静か", "word_id": "W00011", "role": "content"},
        {"t": "です", "grammar_id": "N5_desu", "role": "aux"},
        {"t": "。", "role": "punct"},
    ]))
    assert not any("Inanimate" in i.message for i in issues)


def test_inanimate_quiet_does_NOT_fire_on_park_is_quiet():
    """公園は静かです — places (parks, rooms) take 静か naturally."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "公園", "word_id": "W00016", "role": "content"},
        {"t": "は", "grammar_id": "N5_wa_topic", "role": "particle"},
        {"t": "静か", "word_id": "W00011", "role": "content"},
        {"t": "です", "grammar_id": "N5_desu", "role": "aux"},
        {"t": "。", "role": "punct"},
    ]))
    assert not any("Inanimate" in i.message for i in issues)


def test_inanimate_quiet_fires_on_egg_with_correct_wid():
    """卵 (W00021) is on the inanimate list; 卵は静かです should fire."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "卵", "word_id": "W00021", "role": "content"},
        {"t": "は", "grammar_id": "N5_wa_topic", "role": "particle"},
        {"t": "静か", "word_id": "W00011", "role": "content"},
        {"t": "です", "grammar_id": "N5_desu", "role": "aux"},
        {"t": "。", "role": "punct"},
    ]))
    assert any("Inanimate" in i.message and "卵" in i.message for i in issues)


# ── Rule 11.6: location-を with a noun list joined by と ──────────────────────

def test_location_wo_list_fires_on_rain_evening_park_walk():
    """Canonical defect from the 2026-04-22 closer-rotation audit:
    雨と夕方と公園を歩きます — を-clause coordinates non-traversable
    nouns (rain, evening) with the actual place (park) via と."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "雨", "word_id": "W00002", "role": "content"},
        {"t": "と", "grammar_id": "N5_to_and", "role": "particle"},
        {"t": "夕方", "word_id": "W00018", "role": "content"},
        {"t": "と", "grammar_id": "N5_to_and", "role": "particle"},
        {"t": "公園", "word_id": "W00016", "role": "content"},
        {"t": "を", "grammar_id": "N5_o_object", "role": "particle"},
        {"t": "歩きます", "word_id": "W00017", "role": "content"},
        {"t": "。", "role": "punct"},
    ]))
    assert any(
        "location-を" in i.message and i.severity == "error"
        for i in issues
    ), f"expected location-を error; got: {[i.message for i in issues]}"


def test_location_wo_companion_to_does_NOT_fire():
    """友達と公園を歩きます — companion-と with an animate noun is not
    list-と; this is perfectly natural and must not trip the rule.
    Story 4 s0 was the canonical false-positive in v0.14."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "私", "word_id": "W00003", "role": "content"},
        {"t": "は", "grammar_id": "N5_wa_topic", "role": "particle"},
        {"t": "友達", "word_id": "W00022", "role": "content"},
        {"t": "と", "grammar_id": "N5_to_and", "role": "particle"},
        {"t": "公園", "word_id": "W00016", "role": "content"},
        {"t": "を", "grammar_id": "N5_o_object", "role": "particle"},
        {"t": "歩きます", "word_id": "W00017", "role": "content"},
        {"t": "。", "role": "punct"},
    ]))
    assert not any("location-を" in i.message for i in issues), (
        f"companion-と should not fire location-を rule; got: "
        f"{[i.message for i in issues]}"
    )


def test_location_wo_two_places_does_NOT_fire():
    """公園と外を歩きます — both nouns are traversable places. と here
    is a legitimate list of locations and the rule must not fire."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "公園", "word_id": "W00016", "role": "content"},
        {"t": "と", "grammar_id": "N5_to_and", "role": "particle"},
        {"t": "外", "word_id": "W00005", "role": "content"},
        {"t": "を", "grammar_id": "N5_o_object", "role": "particle"},
        {"t": "歩きます", "word_id": "W00017", "role": "content"},
        {"t": "。", "role": "punct"},
    ]))
    assert not any("location-を" in i.message for i in issues)


def test_location_wo_single_place_does_NOT_fire():
    """公園を歩きます — a single place, no と list. The rule requires
    at least 2 list nouns to fire."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "公園", "word_id": "W00016", "role": "content"},
        {"t": "を", "grammar_id": "N5_o_object", "role": "particle"},
        {"t": "歩きます", "word_id": "W00017", "role": "content"},
        {"t": "。", "role": "punct"},
    ]))
    assert not any("location-を" in i.message for i in issues)


# ── Rule 11.7: closer noun-pile (NEW 2026-04-28) ─────────────────────────────

def _story(sentences):
    """Wrap multiple sentences in story shape for closer-pile tests."""
    return {"sentences": [
        {"idx": i, "tokens": toks} for i, toks in enumerate(sentences)
    ]}


def test_closer_noun_pile_fires_on_story6_closer():
    """Canonical defect: story 6 s7 '雨の朝、猫や花、静かな窓です。'"""
    s0 = [  # any non-closer sentence
        {"t": "私", "word_id": "W00003", "role": "content"},
        {"t": "は", "grammar_id": "N5_wa_topic", "role": "particle"},
        {"t": "見ます", "word_id": "W00006", "role": "content",
         "inflection": {"form": "polite_nonpast"}},
        {"t": "。", "role": "punct"},
    ]
    closer = [
        {"t": "雨", "word_id": "W00002", "role": "content"},
        {"t": "の", "grammar_id": "N5_no_pos", "role": "particle"},
        {"t": "朝", "word_id": "W00015", "role": "content"},
        {"t": "、", "role": "punct"},
        {"t": "猫", "word_id": "W00028", "role": "content"},
        {"t": "や", "grammar_id": "N5_ya_partial", "role": "particle"},
        {"t": "花", "word_id": "W00024", "role": "content"},
        {"t": "、", "role": "punct"},
        {"t": "静か", "word_id": "W00011", "role": "content"},
        {"t": "な", "grammar_id": "N5_na_adj", "role": "particle"},
        {"t": "窓", "word_id": "W00004", "role": "content"},
        {"t": "です", "grammar_id": "N5_desu", "role": "aux"},
        {"t": "。", "role": "punct"},
    ]
    issues = semantic_sanity_lint(_story([s0, closer]))
    assert any("noun-pile" in i.message and i.severity == "error" for i in issues), (
        f"expected closer noun-pile error; got: {[i.message for i in issues]}"
    )


def test_closer_noun_pile_does_NOT_fire_on_verb_closer():
    """猫は窓から私を見ます。 — closer with a real verb. No fire."""
    closer = [
        {"t": "猫", "word_id": "W00028", "role": "content"},
        {"t": "は", "grammar_id": "N5_wa_topic", "role": "particle"},
        {"t": "窓", "word_id": "W00004", "role": "content"},
        {"t": "から", "grammar_id": "N5_kara_from", "role": "particle"},
        {"t": "私", "word_id": "W00003", "role": "content"},
        {"t": "を", "grammar_id": "N5_o_object", "role": "particle"},
        {"t": "見ます", "word_id": "W00006", "role": "content",
         "inflection": {"form": "polite_nonpast"}},
        {"t": "。", "role": "punct"},
    ]
    issues = semantic_sanity_lint(_story([closer]))
    assert not any("noun-pile" in i.message for i in issues)


def test_closer_noun_pile_does_NOT_fire_on_single_noun_predicate():
    """朝です。 — single noun + copula. Not a list, no fire."""
    closer = [
        {"t": "朝", "word_id": "W00015", "role": "content"},
        {"t": "です", "grammar_id": "N5_desu", "role": "aux"},
        {"t": "。", "role": "punct"},
    ]
    issues = semantic_sanity_lint(_story([closer]))
    assert not any("noun-pile" in i.message for i in issues)


def test_closer_noun_pile_does_NOT_fire_when_mo_present():
    """猫も犬も友達です。 — も coordination is deliberate parallelism, escape hatch."""
    closer = [
        {"t": "猫", "word_id": "W00028", "role": "content"},
        {"t": "も", "grammar_id": "N5_mo_also", "role": "particle"},
        {"t": "犬", "word_id": "W00026", "role": "content"},
        {"t": "も", "grammar_id": "N5_mo_also", "role": "particle"},
        {"t": "友達", "word_id": "W00022", "role": "content"},
        {"t": "です", "grammar_id": "N5_desu", "role": "aux"},
        {"t": "。", "role": "punct"},
    ]
    issues = semantic_sanity_lint(_story([closer]))
    assert not any("noun-pile" in i.message for i in issues)


def test_closer_noun_pile_only_fires_on_last_sentence():
    """A noun-pile in s0 (mid-story) must NOT fire — only closers do."""
    pile = [
        {"t": "雨", "word_id": "W00002", "role": "content"},
        {"t": "や", "grammar_id": "N5_ya_partial", "role": "particle"},
        {"t": "風", "word_id": "W00027", "role": "content"},
        {"t": "です", "grammar_id": "N5_desu", "role": "aux"},
        {"t": "。", "role": "punct"},
    ]
    real_closer = [
        {"t": "私", "word_id": "W00003", "role": "content"},
        {"t": "は", "grammar_id": "N5_wa_topic", "role": "particle"},
        {"t": "見ます", "word_id": "W00006", "role": "content",
         "inflection": {"form": "polite_nonpast"}},
        {"t": "。", "role": "punct"},
    ]
    issues = semantic_sanity_lint(_story([pile, real_closer]))
    assert not any("noun-pile" in i.message for i in issues)


# ── Rule 11.8: tautological possessive equivalence (NEW 2026-04-28) ──────────

def test_tautological_equivalence_fires_on_cat_color_rain_color():
    """Canonical defect: story 6 s6 '猫の色は、雨の色です。'"""
    issues = semantic_sanity_lint(_wrap([
        {"t": "猫", "word_id": "W00028", "role": "content"},
        {"t": "の", "grammar_id": "N5_no_pos", "role": "particle"},
        {"t": "色", "word_id": "W00156", "role": "content"},
        {"t": "は", "grammar_id": "N5_wa_topic", "role": "particle"},
        {"t": "、", "role": "punct"},
        {"t": "雨", "word_id": "W00002", "role": "content"},
        {"t": "の", "grammar_id": "N5_no_pos", "role": "particle"},
        {"t": "色", "word_id": "W00156", "role": "content"},
        {"t": "です", "grammar_id": "N5_desu", "role": "aux"},
        {"t": "。", "role": "punct"},
    ]))
    assert any("Tautological" in i.message and "色" in i.message for i in issues), (
        f"expected tautological-possessive error; got: {[i.message for i in issues]}"
    )


def test_tautological_equivalence_does_NOT_fire_on_simple_attribute():
    """猫の色は赤いです — not a possessive equivalence; no fire."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "猫", "word_id": "W00028", "role": "content"},
        {"t": "の", "grammar_id": "N5_no_pos", "role": "particle"},
        {"t": "色", "word_id": "W00156", "role": "content"},
        {"t": "は", "grammar_id": "N5_wa_topic", "role": "particle"},
        {"t": "赤い", "word_id": "W00142", "role": "content"},
        {"t": "です", "grammar_id": "N5_desu", "role": "aux"},
        {"t": "。", "role": "punct"},
    ]))
    assert not any("Tautological" in i.message for i in issues)


def test_tautological_equivalence_does_NOT_fire_on_name_identity():
    """猫の名前は父の名前です — meaningful identity claim, exempt by rule."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "猫", "word_id": "W00028", "role": "content"},
        {"t": "の", "grammar_id": "N5_no_pos", "role": "particle"},
        {"t": "名前", "word_id": "W99001", "role": "content"},  # any wid
        {"t": "は", "grammar_id": "N5_wa_topic", "role": "particle"},
        {"t": "父", "word_id": "W99002", "role": "content"},
        {"t": "の", "grammar_id": "N5_no_pos", "role": "particle"},
        {"t": "名前", "word_id": "W99001", "role": "content"},
        {"t": "です", "grammar_id": "N5_desu", "role": "aux"},
        {"t": "。", "role": "punct"},
    ]))
    assert not any("Tautological" in i.message for i in issues)


# ── Rule 11.9: bare-known-fact extended (NEW 2026-04-28) ─────────────────────

def test_bare_known_fact_extended_fires_on_summer_is_hot():
    """Canonical defect: 「夏は暑い」と思います — universal pairing."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "夏", "word_id": "W99003", "role": "content"},
        {"t": "は", "grammar_id": "N5_wa_topic", "role": "particle"},
        {"t": "暑い", "word_id": "W99004", "role": "content"},
        {"t": "と", "grammar_id": "N4_to_omoimasu", "role": "particle"},
        {"t": "思います", "word_id": "W99005", "role": "content",
         "inflection": {"form": "polite_nonpast"}},
        {"t": "。", "role": "punct"},
    ]))
    assert any("universal-pairing" in i.message for i in issues), (
        f"expected universal-pairing error; got: {[i.message for i in issues]}"
    )


def test_bare_known_fact_extended_does_NOT_fire_on_uncertain_inference():
    """猫は元気だと思います — genuinely inferred state of another being."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "猫", "word_id": "W00028", "role": "content"},
        {"t": "は", "grammar_id": "N5_wa_topic", "role": "particle"},
        {"t": "元気", "word_id": "W99006", "role": "content"},
        {"t": "だ", "grammar_id": "N5_desu", "role": "aux"},
        {"t": "と", "grammar_id": "N4_to_omoimasu", "role": "particle"},
        {"t": "思います", "word_id": "W99005", "role": "content",
         "inflection": {"form": "polite_nonpast"}},
        {"t": "。", "role": "punct"},
    ]))
    assert not any("universal-pairing" in i.message for i in issues)


# ── Rule 11.10: misapplied-quiet adverbial (NEW 2026-04-28) ──────────────────

def test_inanimate_quiet_adverbial_fires_on_book_quietly():
    """本は静かに〜 — book performing action 'quietly'. Inanimate adverbial."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "本", "word_id": "W00033", "role": "content"},
        {"t": "は", "grammar_id": "N5_wa_topic", "role": "particle"},
        {"t": "静かに", "word_id": "W99007", "role": "content"},
        {"t": "あります", "word_id": "W99008", "role": "content",
         "inflection": {"form": "polite_nonpast"}},
        {"t": "。", "role": "punct"},
    ]))
    assert any("acting 静かに" in i.message and "本" in i.message for i in issues), (
        f"expected inanimate adverbial error; got: {[i.message for i in issues]}"
    )


def test_inanimate_quiet_adverbial_does_NOT_fire_on_cat_quietly():
    """猫は静かに見ます — cat IS animate, excluded from rule."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "猫", "word_id": "W00028", "role": "content"},
        {"t": "は", "grammar_id": "N5_wa_topic", "role": "particle"},
        {"t": "静かに", "word_id": "W99007", "role": "content"},
        {"t": "見ます", "word_id": "W00006", "role": "content",
         "inflection": {"form": "polite_nonpast"}},
        {"t": "。", "role": "punct"},
    ]))
    assert not any("acting 静かに" in i.message for i in issues)


def test_inanimate_quiet_adverbial_does_NOT_double_fire_with_11_1():
    """本は静かです — already caught by 11.1; 11.10 must not also fire."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "本", "word_id": "W00033", "role": "content"},
        {"t": "は", "grammar_id": "N5_wa_topic", "role": "particle"},
        {"t": "静か", "word_id": "W00011", "role": "content"},
        {"t": "です", "grammar_id": "N5_desu", "role": "aux"},
        {"t": "。", "role": "punct"},
    ]))
    # 11.1 fires; 11.10 must not also fire on the same sentence.
    quiet_adv = [i for i in issues if "acting 静かに" in i.message]
    assert not quiet_adv, f"11.10 over-fired alongside 11.1: {quiet_adv}"
