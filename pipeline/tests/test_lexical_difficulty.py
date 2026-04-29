"""Lexical-difficulty cap tests for the Monogatari corpus.

Pins the rule introduced 2026-04-29: each story may only mint vocab
words that satisfy EITHER (a) JLPT level ≤ tier cap, OR (b) JMdict
nf-band ≤ tier cap. See `pipeline/lexical_difficulty.py` for the cap
table and the rescue heuristic for JLPT-list gaps (basic-vocab `ichi1`
words like りんご that aren't in the official JLPT lists).

The current corpus has known above-cap entries (e.g. 包丁 N2 in story
3) that pre-date this rule. Per the user's "implement the machinery,
defer the corpus backfill" choice, this test currently runs but is
marked `xfail(strict=False)` so above-cap legacy entries don't block
CI. To convert to a hard block:

  1. Audit the corpus: rewrite above-cap stories to use a more common
     word, OR add the word's surface to the spec's `lexical_overrides`
     field. The audit list comes from this test's failure output.
  2. Once 0 stories fail, change `@pytest.mark.xfail` → no decorator.
  3. Flip `step_vocab_difficulty`'s status="warn" to status="fail" in
     `pipeline/author_loop.py` and add the `halted_at` clause.
  4. Update AGENTS.md "Lexical difficulty cap" section.

The two helper tests ALWAYS run (no xfail) because they only verify the
machinery, not corpus state:

  - test_lexical_difficulty_module_loads — quick smoke test that the
    JLPT data file exists and the module can answer at least one query
    correctly. Catches accidental data-file deletion.
  - test_lexical_difficulty_known_words — pins specific resolutions
    that are sensitive to homograph disambiguation (店|みせ → N5 not
    N1 from 店|てん, etc.) so the lookup logic doesn't silently
    regress.
"""
from __future__ import annotations

import pytest

from lexical_difficulty import (
    Difficulty,
    difficulty_from_vocab_record,
    evaluate_cap,
    lookup_difficulty,
    tier_cap,
)


def test_lexical_difficulty_module_loads():
    """Smoke test: the JLPT data file exists and the lookup returns
    something sane for a known-N5 word.
    """
    diff = lookup_difficulty("卵", "たまご")
    assert isinstance(diff, Difficulty)
    assert diff.jlpt == 5, f"卵/たまご should be JLPT N5, got {diff.jlpt!r}"
    assert diff.nf_band is not None and diff.nf_band <= 10, (
        f"卵/たまご should have a low nf-band, got nf{diff.nf_band}"
    )


@pytest.mark.parametrize(
    "surface,kana,expected_jlpt,note",
    [
        # Common N5 nouns — sanity floor.
        ("卵", "たまご", 5, "egg"),
        ("猫", "ねこ", 5, "cat"),
        ("紙", "かみ", 5, "paper"),
        # Homograph disambiguation. 店 has BOTH 店|てん (N1) and
        # 店|みせ (N5) in the JLPT list; the lookup must resolve to
        # N5 when the spec uses みせ, not N1.
        ("店", "みせ", 5, "shop (homograph: 店|てん is N1)"),
        # Above-cap canonical examples.
        ("包丁", "ほうちょう", 2, "kitchen knife — N2, the bug that motivated this whole feature"),
        ("袋", "ふくろ", 3, "bag — N3"),
        ("皿", "さら", 3, "plate — N3"),
        # JLPT-list-rescue: ichi1-tagged kana-only words missing from
        # the Tanos lists. JLPT level is None, but the rescue path
        # treats them as ≤N5 via the ichi1 commonness tag.
        ("りんご", "りんご", None, "apple — JLPT-list gap, rescued via ichi1"),
        ("バナナ", "バナナ", None, "banana — JLPT-list gap, rescued via ichi1"),
    ],
)
def test_lexical_difficulty_known_words(surface, kana, expected_jlpt, note):
    """Pin specific JLPT resolutions so the lookup logic doesn't
    silently regress (homograph collisions, kana-only matching, etc.).
    """
    diff = lookup_difficulty(surface, kana)
    assert diff.jlpt == expected_jlpt, (
        f"{surface}/{kana} ({note}): expected JLPT {expected_jlpt!r}, got "
        f"{diff.jlpt!r} (source={diff.source!r})"
    )


def test_lexical_difficulty_rescue_path():
    """ichi1-tagged kana-only words (りんご, バナナ) must PASS the
    bootstrap-tier cap even though their JLPT level is None.
    """
    for surface, kana in [("りんご", "りんご"), ("バナナ", "バナナ")]:
        diff = lookup_difficulty(surface, kana)
        assert diff.jlpt is None, f"{surface} should be missing from JLPT list"
        assert "ichi1" in diff.common_tags, (
            f"{surface} should carry ichi1 (basic-vocab) commonness tag"
        )
        dec = evaluate_cap(diff, story_id=1)
        assert not dec.above_cap, (
            f"{surface} should pass story-1 cap via ichi1 rescue, got "
            f"above_cap=True ({dec.reason})"
        )


def test_tier_cap_progression():
    """Sanity-pin the tier table so accidental edits don't silently
    relax (or tighten) the bootstrap cap.
    """
    assert tier_cap(1) == (5, 6), "bootstrap cap should be N5 / nf06"
    assert tier_cap(10) == (5, 6), "story 10 still bootstrap"
    assert tier_cap(11) == (4, 12), "story 11 → N4 / nf12"
    assert tier_cap(25) == (4, 12)
    assert tier_cap(26) == (3, 24)
    assert tier_cap(50) == (3, 24)
    assert tier_cap(51) == (2, 48), "story 51+ ≤N2 / nf48 (any)"


def test_no_above_tier_vocab_without_override(stories, vocab):
    """REGRESSION GUARD: every newly-introduced word in every story
    must satisfy its tier cap, OR appear in the spec's
    `lexical_overrides` list. Words that are "first introduced" in
    story N count against story N's cap; reuses don't.

    Failure repair recipe:
      1. For each flagged word, decide:
         - Rewrite the spec to use a more common alternative (e.g.
           replace 包丁 with the simpler ナイフ N5), OR
         - Add the surface to spec.lexical_overrides if the word is
           genuinely load-bearing for the scene.
      2. Run `pipeline/regenerate_all_stories.py --story N --apply`.
      3. Re-run this test.

    See AGENTS.md "Lexical difficulty cap" section for the full policy.
    """
    # Build per-word "first introduced in" map from vocab_state.
    first_in: dict[str, int] = {}
    for wid, w in vocab.get("words", {}).items():
        fs = w.get("first_story", "")
        if isinstance(fs, str) and fs.startswith("story_"):
            try:
                first_in[wid] = int(fs.split("_")[1])
            except ValueError:
                pass

    # Per-story override list (read from each story's spec).
    from _paths import load_spec

    def _overrides_for(story_id: int) -> set[str]:
        try:
            spec = load_spec(story_id) or {}
            return set(spec.get("lexical_overrides") or [])
        except Exception:
            return set()

    failures: list[str] = []
    for wid, sid in sorted(first_in.items()):
        w = vocab["words"][wid]
        diff = difficulty_from_vocab_record(w)
        dec = evaluate_cap(diff, sid)
        if not dec.above_cap:
            continue
        if w.get("surface", "") in _overrides_for(sid):
            continue
        failures.append(
            f"  {wid} (first in story_{sid}): {w.get('surface')!r}/"
            f"{w.get('kana')!r} jlpt={diff.jlpt} nf={diff.nf_band} "
            f"common={diff.common_tags} — {dec.reason}"
        )
    assert not failures, (
        f"{len(failures)} above-cap mint(s) without `lexical_overrides`:\n"
        + "\n".join(failures)
    )
