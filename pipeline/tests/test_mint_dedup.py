"""Regression test for `text_to_story._ensure_word`'s mint-dedup key.

Background — the bug this guards against:

  Until 2026-04-29, `_ensure_word` keyed `BuildState.minted` (the in-flight
  per-build mint pool) by the on-page SURFACE of each token. For non-
  inflectables (nouns, pronouns) this is fine — the surface IS the
  dictionary form. For inflectables (verbs, i-adjectives, na-adjectives)
  it was a bug: each inflected on-page surface (書きました, 書きます, 書いて,
  書かない, …) would get its own dict-key in `st.minted`, and because
  `vocab_index.lookup` only sees the pre-build vocab_state (NOT in-flight
  mints), the second occurrence of the same lemma in a different inflected
  form would mint a SECOND W-id for the same word.

  Concrete trigger from story 4 ('友達の名前', 2026-04-29 22:35): s1
  使用 「先生は私の名前を書きました。」 minted W00039 = 書く; s5 used
  「私は友達の名前を書きました。」 reused that. But an earlier draft used
  「私は友達の名前を書きます。」 (nonpast) in s5 — that minted W00043 = 書く
  AGAIN. The story registered 9 mints instead of 8 and tripped the
  mint_budget hard-block.

  The fix wires a `_mint_dedup_key(pos1, surface, lemma)` helper that
  returns `pos1|normalized_lemma` for inflectables and `pos1|surface`
  otherwise, then keys `st.minted` by that.

These tests pin both halves of the fix:
  - dual-tense verb collapses to one mint (was two)
  - dual-form i-adjective collapses to one mint (was two; same family of
    bug applies to 大きい / 大きかった etc.)
  - distinct lemmas with the same kana surface still mint separately
    (don't over-dedup)
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from text_to_story import (  # noqa: E402
    _mint_dedup_key,
    build_story,
)


ROOT = Path(__file__).resolve().parents[2]


def _empty_vocab() -> dict:
    """A clean vocab_state with NO words minted yet — so every content
    token in the test spec must be minted by `_ensure_word`. Mirrors the
    schema state_updater expects: top-level `version` + `next_id` + `words`."""
    return {"version": 2, "next_id": 1, "words": {}}


def _empty_grammar() -> dict:
    """A clean grammar_state with NO points covered. The dedup test only
    exercises the vocab path; grammar attribution is irrelevant here."""
    # Load the real grammar catalog so token tagging doesn't crash on
    # missing point lookups, but reset every intro_in_story to None so
    # nothing has been "introduced" yet.
    g = json.loads((ROOT / "data" / "grammar_state.json").read_text())
    for gid, pt in g.get("points", {}).items():
        pt["intro_in_story"] = None
    return g


def _build(spec_sentences: list[dict], vocab: dict, grammar: dict) -> tuple[dict, dict]:
    spec = {
        "story_id": 999,
        "title": {"jp": "テスト", "en": "Test"},
        "sentences": spec_sentences,
    }
    return build_story(spec, vocab, grammar)


def test_dedup_key_keys_inflectables_by_lemma():
    """`_mint_dedup_key` returns lemma-based key for verbs / adjectives."""
    # Verbs: same lemma, different surfaces → same key.
    assert _mint_dedup_key("動詞", "書きました", "書く") == _mint_dedup_key(
        "動詞", "書きます", "書く"
    )
    assert _mint_dedup_key("動詞", "書いて", "書く") == _mint_dedup_key(
        "動詞", "書く", "書く"
    )

    # i-adjective: 大きい / 大きかった → same key.
    assert _mint_dedup_key("形容詞", "大きい", "大きい") == _mint_dedup_key(
        "形容詞", "大きかった", "大きい"
    )

    # na-adjective: 静か / 静かに → same key.
    assert _mint_dedup_key("形状詞", "静か", "静か") == _mint_dedup_key(
        "形状詞", "静かに", "静か"
    )


def test_dedup_key_keys_non_inflectables_by_surface():
    """For nouns/pronouns/adverbs/adnominals the surface IS the dictionary
    form, so keying by surface preserves the pre-fix behavior — distinct
    nouns with distinct surfaces stay distinct."""
    assert _mint_dedup_key("名詞", "鉛筆", "鉛筆") != _mint_dedup_key(
        "名詞", "名前", "名前"
    )
    # Same surface, same POS → same key (would have been the case before too).
    assert _mint_dedup_key("名詞", "鉛筆", "鉛筆") == _mint_dedup_key(
        "名詞", "鉛筆", "鉛筆"
    )


def test_dedup_key_falls_back_to_surface_when_lemma_missing():
    """If the tagger fails to provide a lemma for an inflectable, the key
    falls back to surface so the dedup map stays well-defined (no
    accidental collapse of distinct lexemes under the empty key)."""
    k1 = _mint_dedup_key("動詞", "書きました", "")
    k2 = _mint_dedup_key("動詞", "書きます", "")
    # Different surfaces, no lemma → different keys (NOT collapsed).
    assert k1 != k2


def test_dedup_keys_distinguish_pos():
    """Same string under different POS must not collide. (Pathological
    but cheap to guard.)"""
    assert _mint_dedup_key("名詞", "前", "前") != _mint_dedup_key(
        "動詞", "前", "前"  # nonsense, but tests the key separator
    )


def test_dual_tense_verb_collapses_to_single_mint():
    """The headline regression: a story that uses the same verb in two
    different inflected forms (書きました past + 書きます nonpast) must
    mint the verb ONCE, not twice. Pre-fix this returned 2 W-ids for 書く
    and tripped mint_budget."""
    vocab = _empty_vocab()
    grammar = _empty_grammar()
    sentences = [
        {"jp": "先生は名前を書きました。", "en": "The teacher wrote the name."},
        {"jp": "私は名前を書きます。", "en": "I write the name."},
    ]
    story, report = _build(sentences, vocab, grammar)
    kakus = [m for m in report["new_words"] if m["surface"] == "書く"]
    assert len(kakus) == 1, (
        f"Expected exactly 1 mint for 書く across two inflected forms; "
        f"got {len(kakus)}: {kakus}"
    )
    # Both surface tokens should resolve to the SAME W-id.
    s0_kaku = next(
        (t for t in story["sentences"][0]["tokens"] if t.get("t") == "書きました"),
        None,
    )
    s1_kaku = next(
        (t for t in story["sentences"][1]["tokens"] if t.get("t") == "書きます"),
        None,
    )
    assert s0_kaku is not None and s1_kaku is not None
    assert s0_kaku["word_id"] == s1_kaku["word_id"], (
        f"Two inflected forms of 書く resolve to different W-ids: "
        f"{s0_kaku['word_id']} vs {s1_kaku['word_id']}"
    )


def test_dual_form_iadj_collapses_to_single_mint():
    """Same bug class for i-adjectives: 大きい (nonpast attrib) and
    大きかった (past) share a lemma 大きい — must mint once."""
    vocab = _empty_vocab()
    grammar = _empty_grammar()
    sentences = [
        {"jp": "大きい鉛筆があります。", "en": "There is a big pencil."},
        {"jp": "鉛筆は大きかったです。", "en": "The pencil was big."},
    ]
    _, report = _build(sentences, vocab, grammar)
    ookii = [m for m in report["new_words"] if m["surface"] == "大きい"]
    assert len(ookii) == 1, (
        f"Expected exactly 1 mint for 大きい across two inflected forms; "
        f"got {len(ookii)}: {ookii}"
    )


def test_distinct_lemmas_still_mint_separately():
    """Sanity: the fix must NOT over-dedup. Two genuinely different verbs
    in the same story (見る vs 見せる, both inflected) must each mint."""
    vocab = _empty_vocab()
    grammar = _empty_grammar()
    sentences = [
        {"jp": "私は鉛筆を見ました。", "en": "I saw the pencil."},
        {"jp": "友達は鉛筆を見せました。", "en": "The friend showed the pencil."},
    ]
    _, report = _build(sentences, vocab, grammar)
    surfaces = sorted({m["surface"] for m in report["new_words"] if m.get("pos") == "verb"})
    assert "見る" in surfaces and "見せる" in surfaces, (
        f"Expected both 見る and 見せる minted distinctly; got: {surfaces}"
    )
