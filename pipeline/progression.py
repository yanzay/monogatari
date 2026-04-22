#!/usr/bin/env python3
"""
Length-progression curve for the graded-reader library.

Single source of truth for "how long should story N be?". Used by:
  * pipeline/validate.py        — Check 7 enforces the curve
  * pipeline/planner.py         — validate_plan refuses out-of-band targets
  * pipeline/scaffold.py        — auto-fills target_word_count + max_sentences
  * pipeline/lookup.py          — --next prints recommended size; --progression
                                  lists the full curve

Design intent
-------------
Stories should grow gradually so the learner is always slightly stretched
but never jolted. We grow by sentences (the unit a learner feels) rather
than by tokens (a property of prose density that varies between authors).

Curve:
    target_sentences(n)      = 7 + max(0, (n - 6) // 5)
    target_content_tokens(n) = round(2.6 * target_sentences(n))

This means:
  * Stories 1-10  stay at 7 sentences (~18 content tokens) — the bootstrap
    plateau. Stories 1-8 already shipped at this size; stories 9-10 keep
    the same size so the curve only ever looks back at history.
  * Story 11 is the first +1 step (8 sentences, 21 content tokens).
  * Each subsequent +1 sentence step is spaced 5 stories apart.

Tolerance
---------
Sentences:      target ± 1   (gives the author one beat of latitude)
Content tokens: target × 0.7 .. target × 1.3
                (broad enough to absorb prose-density differences;
                 narrow enough to catch a runaway 50-token monster)
"""
from __future__ import annotations

# How many "starter" stories sit at the baseline before the curve starts climbing.
# Set to 10 so stories 1-10 are all 7 sentences. (Stories 1-8 are already
# shipped at 7; raising this floor would invalidate the existing library.)
_BASELINE_PLATEAU = 10

# How many stories share each subsequent +1-sentence tier.
_TIER_WIDTH = 5

# Baseline sentence count.
_BASE_SENTENCES = 7

# Content-tokens-per-sentence multiplier, calibrated against the existing
# 8-story library (mean ~2.6 content tokens per sentence).
_CONTENT_PER_SENTENCE = 2.6

SENTENCE_TOLERANCE = 1     # target ± this many sentences
CONTENT_LOW = 0.7          # target × this is the minimum content-token count
CONTENT_HIGH = 1.5         # target × this is the maximum content-token count
                           # (raised from 1.4 → 1.5 on 2026-04-22 to give prose
                           # breathing room after Check 6 was relaxed: under the
                           # old reuse-quota regime the cap had to be tight to
                           # stop padding-for-ratio; with Check 6 now an absolute
                           # floor instead of a percentage, the agent no longer
                           # has any incentive to pad, so the upper band can
                           # widen without inviting bloat.)


def target_sentences(story_id: int) -> int:
    """Recommended sentence count for the given story id."""
    if story_id <= _BASELINE_PLATEAU:
        return _BASE_SENTENCES
    extra_tiers = (story_id - _BASELINE_PLATEAU - 1) // _TIER_WIDTH + 1
    return _BASE_SENTENCES + extra_tiers


def target_content_tokens(story_id: int) -> int:
    """Recommended content-token count for the given story id."""
    return round(_CONTENT_PER_SENTENCE * target_sentences(story_id))


def sentence_band(story_id: int) -> tuple[int, int]:
    """(min, max) acceptable sentence count for the story id."""
    t = target_sentences(story_id)
    return max(1, t - SENTENCE_TOLERANCE), t + SENTENCE_TOLERANCE


def content_band(story_id: int) -> tuple[int, int]:
    """(min, max) acceptable content-token count for the story id."""
    t = target_content_tokens(story_id)
    return round(t * CONTENT_LOW), round(t * CONTENT_HIGH)


def progression_table(up_to: int = 50) -> list[dict]:
    """Return a list of dicts describing the curve for stories 1..up_to."""
    rows = []
    for sid in range(1, up_to + 1):
        smin, smax = sentence_band(sid)
        cmin, cmax = content_band(sid)
        rows.append({
            "story_id": sid,
            "target_sentences": target_sentences(sid),
            "sentence_band": (smin, smax),
            "target_content_tokens": target_content_tokens(sid),
            "content_band": (cmin, cmax),
        })
    return rows


def _selftest() -> None:
    print(f"Length-progression curve")
    print(f"  baseline plateau:  stories 1..{_BASELINE_PLATEAU} (7 sentences)")
    print(f"  tier width:        every {_TIER_WIDTH} stories +1 sentence after the plateau")
    print(f"  content density:   {_CONTENT_PER_SENTENCE} content tokens / sentence")
    print(f"  sentence tolerance: ±{SENTENCE_TOLERANCE}")
    print(f"  content tolerance:  {CONTENT_LOW:.0%}..{CONTENT_HIGH:.0%} of target")
    print()
    print(f"{'story':6s} {'sentences':10s} {'sent-band':10s} {'content':9s} {'content-band':14s}")
    last_sent = None
    for r in progression_table(35):
        marker = "  ← +1 step" if last_sent is not None and r["target_sentences"] != last_sent else ""
        print(f"{r['story_id']:<6} {r['target_sentences']:<10} {str(r['sentence_band']):<10} "
              f"{r['target_content_tokens']:<9} {str(r['content_band']):<14}{marker}")
        last_sent = r["target_sentences"]


if __name__ == "__main__":
    _selftest()
