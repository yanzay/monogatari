#!/usr/bin/env python3
"""
Tests for Check 13 (anti-repetition opener guard).

The rule is enforced against new stories (story_id > grandfather_until)
and demoted to warnings for the existing back-catalogue. The tests below
exercise the new-story path (story_id = 9999) to assert the rule fires.
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
    missing, so we provide token lists for title/sentences (using
    role:'punct' to bypass content-token vocab requirements).
    """
    return {
        "story_id": story_id,
        "title": {"jp": title_jp, "en": "test", "tokens": _punct_tokens(title_jp)},
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


# ── Config sanity ──────────────────────────────────────────────────────────


def test_forbidden_patterns_config_is_well_formed():
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    rules = cfg["rules"]
    assert isinstance(rules.get("library_opener_blocklist"), list)
    assert all(isinstance(s, str) and s for s in rules["library_opener_blocklist"])
    assert isinstance(rules.get("consecutive_opener_window"), int)
    assert isinstance(rules.get("consecutive_opener_template_max_chars"), int)
    assert isinstance(rules.get("grandfather_until_story_id"), int)
