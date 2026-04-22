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
        {"t": "は", "grammar_id": "G001_wa_topic", "role": "particle"},
        {"t": "静か", "word_id": "W00011", "role": "content"},
        {"t": "です", "grammar_id": "G003_desu", "role": "aux"},
        {"t": "。", "role": "punct"},
    ]))
    assert any("Inanimate" in i.message and "本" in i.message for i in issues)


def test_inanimate_quiet_does_NOT_fire_on_evening_is_quiet():
    """夕方は静かです is perfectly natural JP. The original list mistakenly
    contained W00018 (夕方) under the comment '卵'; v0.14 substituted in
    the real 卵 id (W00021)."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "夕方", "word_id": "W00018", "role": "content"},
        {"t": "は", "grammar_id": "G001_wa_topic", "role": "particle"},
        {"t": "静か", "word_id": "W00011", "role": "content"},
        {"t": "です", "grammar_id": "G003_desu", "role": "aux"},
        {"t": "。", "role": "punct"},
    ]))
    assert not any("Inanimate" in i.message for i in issues)


def test_inanimate_quiet_does_NOT_fire_on_park_is_quiet():
    """公園は静かです — places (parks, rooms) take 静か naturally."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "公園", "word_id": "W00016", "role": "content"},
        {"t": "は", "grammar_id": "G001_wa_topic", "role": "particle"},
        {"t": "静か", "word_id": "W00011", "role": "content"},
        {"t": "です", "grammar_id": "G003_desu", "role": "aux"},
        {"t": "。", "role": "punct"},
    ]))
    assert not any("Inanimate" in i.message for i in issues)


def test_inanimate_quiet_fires_on_egg_with_correct_wid():
    """卵 (W00021) is on the inanimate list; 卵は静かです should fire."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "卵", "word_id": "W00021", "role": "content"},
        {"t": "は", "grammar_id": "G001_wa_topic", "role": "particle"},
        {"t": "静か", "word_id": "W00011", "role": "content"},
        {"t": "です", "grammar_id": "G003_desu", "role": "aux"},
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
        {"t": "と", "grammar_id": "G010_to_and", "role": "particle"},
        {"t": "夕方", "word_id": "W00018", "role": "content"},
        {"t": "と", "grammar_id": "G010_to_and", "role": "particle"},
        {"t": "公園", "word_id": "W00016", "role": "content"},
        {"t": "を", "grammar_id": "G005_wo_object", "role": "particle"},
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
        {"t": "は", "grammar_id": "G001_wa_topic", "role": "particle"},
        {"t": "友達", "word_id": "W00022", "role": "content"},
        {"t": "と", "grammar_id": "G010_to_and", "role": "particle"},
        {"t": "公園", "word_id": "W00016", "role": "content"},
        {"t": "を", "grammar_id": "G005_wo_object", "role": "particle"},
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
        {"t": "と", "grammar_id": "G010_to_and", "role": "particle"},
        {"t": "外", "word_id": "W00005", "role": "content"},
        {"t": "を", "grammar_id": "G005_wo_object", "role": "particle"},
        {"t": "歩きます", "word_id": "W00017", "role": "content"},
        {"t": "。", "role": "punct"},
    ]))
    assert not any("location-を" in i.message for i in issues)


def test_location_wo_single_place_does_NOT_fire():
    """公園を歩きます — a single place, no と list. The rule requires
    at least 2 list nouns to fire."""
    issues = semantic_sanity_lint(_wrap([
        {"t": "公園", "word_id": "W00016", "role": "content"},
        {"t": "を", "grammar_id": "G005_wo_object", "role": "particle"},
        {"t": "歩きます", "word_id": "W00017", "role": "content"},
        {"t": "。", "role": "punct"},
    ]))
    assert not any("location-を" in i.message for i in issues)
