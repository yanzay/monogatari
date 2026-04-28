"""Regression tests for the word-audio TTS input string.

Bug (2026-04-29): single-kanji words were being read by Google
ja-JP-Neural2-B with their on-yomi instead of the intended kun-yomi
reading. Concretely, the word 道 (kana=みち, romaji=michi, meaning
"road/path") was being spoken as 「どう」 because TTS defaults to
on-yomi when given a kanji in isolation with no surrounding context.

The systemic fix: feed TTS the unambiguous KANA reading instead of the
surface form. Sentence audio is unaffected — sentences carry their
own grammatical context and surrounding particles disambiguate
readings naturally — but isolated word audio MUST use kana.

These tests pin the contract on word_audio_text() so a future
"helpfully" prefer-surface change surfaces immediately.
"""
from pipeline.audio_builder import word_audio_text


def test_returns_kana_when_present():
    """The kana field is the unambiguous reading; always preferred."""
    assert word_audio_text({"surface": "道", "kana": "みち"}) == "みち"


def test_returns_kana_for_multichar_kanji_word():
    """Multi-kanji words also benefit from kana — readings can be irregular."""
    assert word_audio_text({"surface": "友達", "kana": "ともだち"}) == "ともだち"


def test_returns_surface_for_pure_hiragana_word():
    """When surface == kana there's no behavioral change vs. legacy."""
    out = word_audio_text({"surface": "あさ", "kana": "あさ"})
    assert out == "あさ"


def test_returns_kana_even_when_surface_is_kanji_compound():
    """Mixed kanji + okurigana words: kana is the only safe input."""
    assert word_audio_text({"surface": "見ます", "kana": "みます"}) == "みます"


def test_falls_back_to_surface_when_kana_missing():
    """Defensive: pre-2026 corpus might have surface-only entries."""
    assert word_audio_text({"surface": "道"}) == "道"


def test_falls_back_to_surface_when_kana_empty_string():
    """Treat empty kana as missing — Python's `or` already covers this."""
    assert word_audio_text({"surface": "道", "kana": ""}) == "道"


def test_returns_empty_string_when_word_is_none():
    """Caller substitutes the word_id when this returns falsy."""
    assert word_audio_text(None) == ""


def test_returns_empty_string_when_word_is_empty_dict():
    assert word_audio_text({}) == ""


def test_returns_empty_string_when_neither_field_present():
    assert word_audio_text({"reading": "michi"}) == ""


# ── REGRESSION: every single-kanji single-syllable word that historically
#    tripped on-yomi gets the right kun-yomi text ──────────────────────────


def test_problem_words_from_screenshot_get_kana():
    """The exact words that motivated this fix."""
    cases = [
        ({"surface": "道", "kana": "みち"}, "みち"),
        ({"surface": "月", "kana": "つき"}, "つき"),
        ({"surface": "手", "kana": "て"}, "て"),
        ({"surface": "家", "kana": "いえ"}, "いえ"),
        ({"surface": "鍵", "kana": "かぎ"}, "かぎ"),
        ({"surface": "朝", "kana": "あさ"}, "あさ"),
        ({"surface": "私", "kana": "わたし"}, "わたし"),
    ]
    for word, expected in cases:
        assert word_audio_text(word) == expected, f"{word!r} → expected {expected!r}"
