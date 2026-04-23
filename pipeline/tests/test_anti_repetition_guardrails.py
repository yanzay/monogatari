#!/usr/bin/env python3
"""
Tests for Check 13 (anti-repetition opener guard) and Check 14 (title must
not be the new-grammar surface form).

Both rules are enforced against new stories (story_id > grandfather_until)
and demoted to warnings for the existing back-catalogue. The tests below
exercise the new-story path (story_id = 9999) to assert the rules fire.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from validate import validate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
VOCAB_PATH = ROOT / "data" / "vocab_state.json"
GRAMMAR_PATH = ROOT / "data" / "grammar_state.json"
CFG_PATH = Path(__file__).resolve().parent.parent / "forbidden_patterns.json"


def _vocab() -> dict:
    return json.loads(VOCAB_PATH.read_text(encoding="utf-8"))


def _grammar() -> dict:
    return json.loads(GRAMMAR_PATH.read_text(encoding="utf-8"))


def _punct_tokens(text: str) -> list:
    """Render `text` as a list of single-char punct tokens (so we get the
    surface form joined back without needing real word_ids)."""
    return [{"t": ch, "role": "punct"} for ch in text]


def _make_story(*, story_id: int, opener_jp: str, title_jp: str = "テスト",
                new_grammar=None) -> dict:
    """Minimal story stub that exercises only the opener + title checks.

    The validator's Check 1 short-circuits if required schema fields are
    missing, so we provide token lists for title/subtitle/sentences (using
    role:'punct' to bypass content-token vocab requirements).
    """
    return {
        "story_id": story_id,
        "title": {"jp": title_jp, "en": "test", "tokens": _punct_tokens(title_jp)},
        "subtitle": {"jp": "サブ", "en": "sub", "tokens": _punct_tokens("サブ")},
        "new_words": [],
        "new_grammar": new_grammar or [],
        "all_words_used": [],
        "sentences": [
            {
                "idx": 0,
                "tokens": _punct_tokens(opener_jp) + [{"t": "。", "role": "punct"}],
                "gloss_en": "test.",
            }
        ],
    }


def _check_codes(result, code: int) -> list:
    return [e for e in result.errors if e.check == code]


def _check13_warnings(result) -> list:
    return [w for w in result.warnings if "[Check 13" in w]


def _check14_warnings(result) -> list:
    return [w for w in result.warnings if "[Check 14" in w]


# ── Check 13: opener guard ─────────────────────────────────────────────────


def test_check13_blocklist_fires_on_new_story():
    """A new story (id > grandfather_until) using a blocklisted opener must
    produce a Check 13 error."""
    story = _make_story(story_id=9999, opener_jp="春の夕方です")
    result = validate(story, _vocab(), _grammar())
    assert _check_codes(result, 13), \
        "Check 13 must fire for a new story opening with a blocklisted template"


def test_check13_blocklist_grandfathered_emits_warning_only():
    """A story_id within the grandfather range must demote the error to a
    warning so the existing library still ships."""
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    grandfather_id = int(cfg["rules"]["grandfather_until_story_id"])
    story = _make_story(story_id=grandfather_id, opener_jp="春の夕方です")
    result = validate(story, _vocab(), _grammar())
    assert not _check_codes(result, 13), \
        "Check 13 must not error for grandfathered stories"
    assert _check13_warnings(result), \
        "Check 13 must still emit a warning for grandfathered violations"


def test_check13_clean_opener_passes():
    """A new opener that doesn't match the blocklist or any prior story
    must not trigger Check 13."""
    story = _make_story(story_id=9999, opener_jp="夜中、机の上で")
    result = validate(story, _vocab(), _grammar())
    assert not _check_codes(result, 13)
    assert not _check13_warnings(result)


# ── Check 14: title-as-grammar-form ────────────────────────────────────────


def test_check14_fires_when_title_equals_grammar_surface():
    """A new story whose title is exactly the new-grammar surface form must
    produce a Check 14 error.

    G046_masen_deshita has surface '待ちませんでした' (and similar). We use
    the actual catalog entry so the test reflects production behavior.
    """
    grammar = _grammar()
    # Find a grammar point with a concrete surface form to test against.
    test_gid, test_surface = None, None
    for gid, g in grammar.get("points", {}).items():
        surfaces = g.get("surfaces") or g.get("surface_forms") or []
        if isinstance(surfaces, list):
            for s in surfaces:
                if isinstance(s, str) and 3 <= len(s) <= 12:
                    test_gid, test_surface = gid, s
                    break
        if test_gid:
            break
    if not test_gid:
        # No catalog grammar exposes a 'surfaces' field — Check 14 can't fire
        # for any story, so skip rather than fail.
        import pytest
        pytest.skip("No grammar point with a surface form in catalog; Check 14 N/A")

    story = _make_story(
        story_id=9999,
        opener_jp="夜中、机の上で",
        title_jp=test_surface,
        new_grammar=[test_gid],
    )
    result = validate(story, _vocab(), grammar)
    assert _check_codes(result, 14), \
        f"Check 14 must fire when title == new-grammar surface ({test_surface})"


def test_check14_clean_title_passes():
    """A title that does not echo the grammar form must not trigger Check 14."""
    story = _make_story(
        story_id=9999,
        opener_jp="夜中、机の上で",
        title_jp="月の影",
        new_grammar=["G059_dakara"],
    )
    result = validate(story, _vocab(), _grammar())
    assert not _check_codes(result, 14)


# ── Config sanity ──────────────────────────────────────────────────────────


def test_forbidden_patterns_config_is_well_formed():
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    rules = cfg["rules"]
    assert isinstance(rules.get("library_opener_blocklist"), list)
    assert all(isinstance(s, str) and s for s in rules["library_opener_blocklist"])
    assert isinstance(rules.get("consecutive_opener_window"), int)
    assert isinstance(rules.get("consecutive_opener_template_max_chars"), int)
    assert isinstance(rules.get("grandfather_until_story_id"), int)
    assert isinstance(rules.get("title_must_not_equal_grammar_form"), bool)
