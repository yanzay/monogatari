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


# ── Cadence policy: minimum & maximum new-grammar introduction rate ──────────
#
# Research basis (synthesised 2026-04-22):
#   * Sakurai et al. style incidental-reading studies show ~40 encounters of
#     a grammar form let learners reliably *notice and partially acquire* it,
#     while ~10 encounters were insufficient. (Encounter ≈ one token use in
#     comprehensible input.)
#   * Skill-acquisition research (DeKeyser 2017, Nation 2022) emphasises
#     "structured recycling" — the journey from declarative awareness to
#     procedural automaticity needs many more exposures than initial
#     recognition. Estimates put proceduralisation an order of magnitude
#     beyond first-notice.
#   * Spacing effect (Suzuki 2021) means encounters spread across many
#     stories beat the same count crammed into one or two.
#
# Translated to this project (where "encounter" = one story that uses the
# point at least once, since each story is a self-contained reading session):
#
#   ── Internalisation thresholds ────────────────────────────────────────────
#   ENCOUNTERS_TO_NOTICE       = 10  — point is "in awareness"
#   ENCOUNTERS_TO_INTERNALISE  = 40  — point is "incidentally acquired"
#   ENCOUNTERS_TO_PROCEDURALISE= 80  — point is "automatic" (10× factor /2)
#
#   ── Cadence rules ─────────────────────────────────────────────────────────
#   Rule A (max):  no story may introduce more than MAX_NEW_PER_STORY new
#                  grammar points (after the bootstrap window). Cramming
#                  hurts consolidation.
#   Rule B (min):  across any rolling window of CADENCE_WINDOW consecutive
#                  stories (after the bootstrap window) the library must
#                  introduce ≥ MIN_NEW_PER_WINDOW new points. Stagnation
#                  starves the ladder of forward motion.
#   Bootstrap:     stories 1..BOOTSTRAP_END are exempt from both rules but
#                  capped at BOOTSTRAP_MAX_TOTAL introductions in aggregate
#                  (the foundational copula + particle set).
#
# Total runway to full catalog coverage (slow-but-steady):
#   N_intros_after_bootstrap  = CATALOG_TOTAL − BOOTSTRAP_MAX_TOTAL
#   stories_needed            ≈ N_intros_after_bootstrap × CADENCE_WINDOW
#                               / MIN_NEW_PER_WINDOW + BOOTSTRAP_END
#   For 141 catalog points and the defaults below: ~3·(141−9)+3 ≈ 399 stories.
#   This is intentionally a multi-year reading habit, in line with the
#   five-to-seven-year CALP timeline reported in SLA literature.

ENCOUNTERS_TO_NOTICE = 10
ENCOUNTERS_TO_INTERNALISE = 40
ENCOUNTERS_TO_PROCEDURALISE = 80

BOOTSTRAP_END = 3            # stories 1..3 may load the foundational set
BOOTSTRAP_MAX_TOTAL = 11     # aggregate cap for the bootstrap window
                             # (matches the foundational copula+particle set
                             # actually loaded in stories 1-2 of the library)
MAX_NEW_PER_STORY = 1        # after bootstrap: at most one introduction per story
CADENCE_WINDOW = 5           # rolling window (stories) for the minimum rule
MIN_NEW_PER_WINDOW = 1       # at least this many introductions per window
MAX_CONSEC_CONSOLIDATION = 4 # max consecutive stories that may opt out via
                             # consolidation_arc=true. Caps "stagnation arcs"
                             # tightly: at this rate every grammar point gets
                             # several reinforcement stories before another
                             # competing intro arrives.

# Reinforcement window: a freshly-introduced grammar point must be re-used
# (i.e. appear in at least one token) in at least MIN_REINFORCEMENT_USES of
# the next REINFORCEMENT_WINDOW stories that follow its introduction.
# This is the input side of the 40-encounter internalisation curve — without
# repeated exposure, the introduction is wasted.
REINFORCEMENT_WINDOW = 5     # check the next 5 stories after introduction
MIN_REINFORCEMENT_USES = 1   # the point must appear in ≥1 of those 5 stories
                             # (a single follow-up encounter is the minimum
                             # signal that the introduction has any future
                             # role; missing it means the point was a one-shot
                             # and the introduction was wasted)


def cadence_max_per_story(story_id: int) -> int:
    """Maximum legal number of new grammar introductions in this story."""
    if story_id <= BOOTSTRAP_END:
        return BOOTSTRAP_MAX_TOTAL  # the bootstrap window is policed in aggregate
    return MAX_NEW_PER_STORY


def cadence_window_for(story_id: int) -> tuple[int, int] | None:
    """
    Return the (lo, hi) inclusive story-id window that *ends* at story_id and
    is subject to the minimum-cadence rule. Returns None if the window falls
    inside or straddles the bootstrap region (where the rule does not apply).

    A window of CADENCE_WINDOW consecutive stories is only enforced once both
    its endpoints sit beyond BOOTSTRAP_END.
    """
    lo = story_id - CADENCE_WINDOW + 1
    if lo <= BOOTSTRAP_END:
        return None
    return (lo, story_id)


def expected_total_runway(catalog_total: int) -> int:
    """
    Approximate number of stories needed to introduce every catalog point at
    the minimum-cadence rate (slow-but-steady ceiling).
    """
    after_bootstrap = max(0, catalog_total - BOOTSTRAP_MAX_TOTAL)
    return BOOTSTRAP_END + after_bootstrap * CADENCE_WINDOW // MIN_NEW_PER_WINDOW


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
    print()
    print("── Cadence policy (slow-but-steady) ──")
    print(f"  Bootstrap window:        stories 1..{BOOTSTRAP_END}, cap {BOOTSTRAP_MAX_TOTAL} intros total")
    print(f"  Max new per story:       {MAX_NEW_PER_STORY} (after bootstrap)")
    print(f"  Min new per {CADENCE_WINDOW}-story window: {MIN_NEW_PER_WINDOW}")
    print(f"  Internalisation curve:   notice={ENCOUNTERS_TO_NOTICE}, "
          f"acquire={ENCOUNTERS_TO_INTERNALISE}, "
          f"automatic={ENCOUNTERS_TO_PROCEDURALISE} encounters")


if __name__ == "__main__":
    show_curve()
    print()
    print("── per-story tier ──")
    for sid in [1, 5, 10, 11, 15, 25, 26, 50, 51]:
        print(f"  story {sid:>3}: tier {active_tier(sid)} ({active_jlpt(sid)})")
