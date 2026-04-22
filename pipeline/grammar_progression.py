"""
Grammar tier progression — sister module to pipeline/progression.py.

Where progression.py governs *length* (sentences + content tokens per story),
this module governs *grammatical complexity*: which JLPT-tier grammar points
are eligible to be introduced at each story_id.

Design (per spec discussion):
  - Tiers correspond to JLPT levels (N5 → N4 → N3 → N2/N1) but the project
    is JLPT-aligned only as a reference framework — we don't claim to teach
    the exam. JLPT is the closest commonly-understood ladder; using it
    eliminates the "is this beginner or intermediate?" judgment call.
  - Each grammar point in data/grammar_state.json carries a "jlpt" field
    ("N5" / "N4" / "N3" / "N2" / "N1"). This module maps that to a tier
    number (1..4) and an eligibility window per story_id.
  - Validator's Check 3.5 enforces: a story's new_grammar may only come
    from the current tier OR an earlier tier. Cross-tier introductions
    block the build (consistent with how Check 7 length progression works).

Tier windows (sketched on 2026-04-22; adjust as the library matures):
  Tier 1 (N5)  — stories  1 – 10
  Tier 2 (N4)  — stories 11 – 25
  Tier 3 (N3)  — stories 26 – 50
  Tier 4 (N2+) — stories 51+

A story is *in* a tier (its "active tier") when story_id falls in that
window. Story_id 11 is therefore the earliest legal moment to introduce
an N4 grammar point.

Earlier-tier points remain legal forever — story 50 may absolutely
introduce a previously-skipped N5 particle if the right narrative
context arises. The block is one-directional (no jumping ahead).
"""

from __future__ import annotations


# ── Tier definition ───────────────────────────────────────────────────────────

# Story_id windows per tier. End is inclusive. "None" means open-ended.
TIER_WINDOWS: list[tuple[int, int, int | None, str]] = [
    (1, 1,  10,   "N5"),
    (2, 11, 25,   "N4"),
    (3, 26, 50,   "N3"),
    (4, 51, None, "N2"),  # N2/N1 collapse into Tier 4 for now
]

# JLPT level → tier number lookup.
JLPT_TO_TIER: dict[str, int] = {
    "N5": 1,
    "N4": 2,
    "N3": 3,
    "N2": 4,
    "N1": 4,
}


def active_tier(story_id: int) -> int:
    """Return the tier number (1..4) a story_id falls into."""
    for tier, lo, hi, _ in TIER_WINDOWS:
        if story_id >= lo and (hi is None or story_id <= hi):
            return tier
    return 1  # safety fallback


def active_jlpt(story_id: int) -> str:
    """Return the JLPT label ('N5'..'N2') for a story_id."""
    tier = active_tier(story_id)
    for t, _, _, jlpt in TIER_WINDOWS:
        if t == tier:
            return jlpt
    return "N5"


def grammar_tier(jlpt_or_label: str | None) -> int | None:
    """Map a grammar point's jlpt field to its tier number, or None if unset."""
    if not jlpt_or_label:
        return None
    label = jlpt_or_label.strip().upper()
    return JLPT_TO_TIER.get(label)


def is_grammar_legal_for_story(jlpt_or_label: str | None, story_id: int) -> bool:
    """
    Return True if a grammar point with the given jlpt label may legally be
    *introduced* in a story with the given story_id.

    Earlier-tier grammar is always legal. Same-tier is legal once we're in
    the window. Later-tier is rejected — cross-tier jumps must wait.
    Grammar points with no jlpt label are conservatively allowed (so legacy
    points without classification don't break the build).
    """
    tier = grammar_tier(jlpt_or_label)
    if tier is None:
        return True  # unclassified — let it through (back-compat)
    return tier <= active_tier(story_id)


def tier_label(tier: int) -> str:
    """Human-readable label for a tier."""
    for t, _, _, jlpt in TIER_WINDOWS:
        if t == tier:
            return f"Tier {tier} (JLPT {jlpt})"
    return f"Tier {tier}"


def show_curve() -> None:
    """Print the tier ladder for the lookup --grammar-progression CLI."""
    print("── Grammar tier progression (JLPT-aligned) ──\n")
    print(f"{'tier':<6} {'JLPT':<5} {'window':<14} {'meaning':<60}")
    meanings = {
        "N5": "absolute foundation: copula, particles, te-form, te-iru, basic connectives",
        "N4": "tense + negation: past, negatives, ~たい (want), ~から (because), simple adverbs",
        "N3": "intent + conditionals: ~ましょう, ~たら, ~ば, ~つもり, comparison, time clauses",
        "N2": "embedded clauses, passive/causative, honorifics, advanced connectives",
    }
    for tier, lo, hi, jlpt in TIER_WINDOWS:
        window = f"{lo}–{hi}" if hi is not None else f"{lo}+"
        print(f"  {tier:<4} {jlpt:<5} stories {window:<6} {meanings.get(jlpt, '')}")
    print("\n  Rule: a story's new_grammar may come from the current tier OR earlier.")
    print("  Cross-tier introductions (jumping ahead) are blocked by Check 3.5.")


if __name__ == "__main__":
    show_curve()
    print()
    print("── per-story tier ──")
    for sid in [1, 5, 10, 11, 15, 25, 26, 50, 51]:
        print(f"  story {sid:>3}: tier {active_tier(sid)} ({active_jlpt(sid)})")
