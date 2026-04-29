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

## ── Bootstrap ladder (Phase 4 reload, 2026-04-29) ──────────────────────────
##
## Replaces the legacy single-int `BOOTSTRAP_END = 3` policy. The new
## bootstrap window is 10 stories, and each story has explicit
## per-story (vocab_min, vocab_max, grammar_min, grammar_max) caps
## that taper from a wide front-load (story 1: 14–18 mints + 6–8
## grammar) down to the steady-state policy (1 grammar / 3–5 vocab)
## by story 11.
##
## Why a ladder, not a single constant: the v2.0 corpus (10 stories
## under the legacy 1-grammar / ~5-vocab policy) convergence-failed on
## the same defect the v1 audit identified — a tight palette can only
## express tight stories. See `docs/phase4-bootstrap-reload-2026-04-29.md`
## §3 for the derivation. The ladder is paired with `data/v2_5_seed_plan.json`
## which prescribes WHICH words/grammar each slot mints, so the wider
## caps go to planned diversity, not opportunistic adjacency.
##
## Schema for each row:
##   (vocab_min, vocab_max, grammar_min, grammar_max, scene_class)
##
## - `vocab_min` / `vocab_max`: per-story bounds on the count of new
##   word IDs minted. Validator's mint_budget step enforces max;
##   `test_vocabulary_introduction_cadence` enforces min.
## - `grammar_min` / `grammar_max`: per-story bounds on the count of
##   new grammar points introduced. Validator's coverage_floor enforces
##   min; `test_grammar_introduction_cadence` enforces max.
## - `scene_class`: the planned scene_class for the slot. Surfaced in
##   the brief as `must_hit.seed_plan.scene`. The agent may override
##   this only by spending a §G override (and the override has to be
##   documented in the spec's `intent`). Defaults the §B.1 forbid.py
##   tool's "scene novelty" check.
##
## Stories 11+ fall through to the legacy policy
## (MAX_NEW_PER_STORY=1, MIN_NEW_WORDS_PER_STORY=3, no scene constraint).
BOOTSTRAP_LADDER: dict[int, dict] = {
    # Story 1 grammar_max raised to 10 (was 8) on 2026-04-29 after the
    # first author cycle hit the day-1 minimum-viable-grammar floor:
    # の (possessive), へ (direction), も (also) are unavoidable in any
    # natural opening sentence and the original seed plan undercounted
    # them. The plan doc's "complete N5 by story ~12" arithmetic still
    # holds — story 1 just carries 10 of the 54 N5 points instead of 8,
    # and the taper continues from there.
    # Story 1 grammar_max raised again 10 → 11 on 2026-04-29 (post-ship)
    # because G021_aru_iru is auto-attributed on first use of あります OR
    # います AND counts as a corpus grammar intro even though it's a
    # paradigm pair, not a discrete grammar point. The seed plan didn't
    # list it explicitly because it's never an "intro" in the
    # learner-facing sense — it's the existence-verb pair you cannot
    # avoid touching whenever you write either あります or います. Treat
    # G021_aru_iru as a free auto-tag (counted, but not budgeted).
    1:  {"vocab_min": 14, "vocab_max": 18, "grammar_min":  8, "grammar_max": 11, "scene_class": "home_morning"},
    2:  {"vocab_min":  6, "vocab_max": 10, "grammar_min": 3, "grammar_max": 5, "scene_class": "walk_to_shop"},
    3:  {"vocab_min":  5, "vocab_max":  8, "grammar_min": 3, "grammar_max": 4, "scene_class": "kitchen"},
    4:  {"vocab_min":  5, "vocab_max":  8, "grammar_min": 2, "grammar_max": 4, "scene_class": "classroom"},
    5:  {"vocab_min":  4, "vocab_max":  7, "grammar_min": 2, "grammar_max": 4, "scene_class": "station"},
    6:  {"vocab_min":  4, "vocab_max":  7, "grammar_min": 2, "grammar_max": 3, "scene_class": "park_bench"},
    7:  {"vocab_min":  4, "vocab_max":  6, "grammar_min": 2, "grammar_max": 3, "scene_class": "rainy_doorway"},
    8:  {"vocab_min":  3, "vocab_max":  6, "grammar_min": 1, "grammar_max": 3, "scene_class": "shop_counter"},
    9:  {"vocab_min":  3, "vocab_max":  5, "grammar_min": 1, "grammar_max": 2, "scene_class": "phone_call"},
    10: {"vocab_min":  3, "vocab_max":  5, "grammar_min": 1, "grammar_max": 2, "scene_class": "rooftop"},
}

BOOTSTRAP_END = max(BOOTSTRAP_LADDER.keys())   # = 10 under the v2.5 ladder
BOOTSTRAP_MAX_TOTAL = sum(row["vocab_max"] for row in BOOTSTRAP_LADDER.values())  # informational; was 15 under the legacy single-int policy.

## ── Steady-state policy (story 11+) ────────────────────────────────────────
## After the bootstrap ladder taper, the per-story cap collapses to a
## single new grammar point. This is the legacy v2.0 steady-state policy
## and remains correct for stories where the existing palette is broad
## enough to express varied stories from a single new pick.
MAX_NEW_PER_STORY = 1        # after bootstrap (story 11+): at most one grammar intro / story
CADENCE_WINDOW = 5           # rolling window (stories) for the minimum rule
MIN_NEW_PER_WINDOW = 1       # at least this many introductions per window

# ── Vocabulary cadence (separate from the grammar cadence above) ──────────
# After the bootstrap window, every story must introduce at least
# MIN_NEW_WORDS_PER_STORY new vocabulary items. The pedagogical motivation
# is the same as the grammar cadence: a graded reader that stops growing
# its vocabulary stops being a graded reader. Three new content words per
# story is the planner's long-standing default (see planner.py:--n-new-words)
# and matches the rate at which the curated catalogs grow.
#
# Bootstrap stories (story_id <= BOOTSTRAP_END) are exempt because story 1
# loads ~14 foundational nouns at once, which would make a uniform floor
# misleading. After bootstrap the floor is hard.
MIN_NEW_WORDS_PER_STORY = 3

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

# ── Vocabulary reinforcement cadence ──────────────────────────────────────────
#
# Newly-introduced words also need early reinforcement — introducing a word
# once and never revisiting it for dozens of stories defeats the purpose of
# the spaced-repetition reading approach.
#
# Two complementary rules:
#
#   Rule R1 (early reinforcement):
#     A word introduced in story_N must appear again in at least
#     VOCAB_REINFORCE_MIN_USES of the next VOCAB_REINFORCE_WINDOW stories
#     (story N+1 … N+W). This catches "one-and-done" introductions while
#     the word is still warm in working memory.
#
#     Window: 10 stories. Minimum reuses: 1.
#     Rationale: The grammar reinforcement window (5/1) is calibrated for
#     grammar *structures*, which are reused implicitly via any sentence.
#     Content vocabulary needs more deliberate repetition because it isn't
#     automatically carried by every sentence. Ten stories gives the author
#     enough runway to weave the word back in naturally without forcing it
#     into every subsequent story. The minimum bar is ONE follow-up
#     reinforcement: a single re-encounter within the window is enough
#     signal that the introduction wasn't a one-shot. (Relaxed 2026-04-28
#     from 2 → 1 because the previous 2-hit bar created structural debt
#     that propagated cascades onto adjacent already-shipped stories.) This
#     maps to ENCOUNTERS_TO_NOTICE (10) as the long-run target; the
#     early-window check is the on-ramp.
#
#   Rule R2 (no abandoned words) — RETIRED 2026-04-24:
#     The previous formulation policed the longest gap between consecutive
#     uses of a word over the *entire library lifetime*, capped at 20
#     stories. In practice this actively discouraged organic late reuse:
#     a word last seen at story 26 could not be casually echoed in story
#     50 without either (a) cascading reinforcement weaves through every
#     gap story 27..49 or (b) leaving the word silent forever. Authors
#     ended up treating each word as either "alive" (reinforced every ≤20
#     stories) or "dead" (never used again) — there was no middle ground
#     for a sentimental callback or a thematic echo.
#
#     The pedagogical intent — *teach a new word properly when it debuts*
#     — is fully covered by Rule R1 above. Once a word has cleared its
#     10-story maturation window with ≥2 reinforcements, the learner has
#     had real exposure to it. Anything later is the author's editorial
#     choice; it is encouraged but never required.
#
#     The constants below are kept for backward compatibility with any
#     external tooling that imports them, but the validator and pytest
#     check are now no-ops. See test_no_vocab_word_abandoned for the
#     deprecation notice.
#
VOCAB_REINFORCE_WINDOW   = 10   # look at the next 10 stories after introduction
VOCAB_REINFORCE_MIN_USES = 1    # must appear in ≥1 of those 10 stories
                                # (relaxed 2026-04-28 from 2 → 1; see Rule R1
                                #  rationale block above)
# (VOCAB_MAX_GAP and VOCAB_ABANDON_GRACE — the R2 abandonment-rule constants —
#  were retired 2026-04-24 along with the rule itself.)



def ladder_for(story_id: int) -> dict:
    """Return the per-story ladder row for `story_id`, or the steady-state
    fallback for stories outside the bootstrap window.

    Schema (always present, never None):
        {
          "vocab_min":     int,    # min new words this story must mint
          "vocab_max":     int,    # max new words this story may mint
          "grammar_min":   int,    # min new grammar points this story must intro
          "grammar_max":   int,    # max new grammar points this story may intro
          "scene_class":   str|None,
                                   # planned scene_class for the slot;
                                   # None for stories 11+ (no constraint)
          "in_bootstrap":  bool,   # True iff this slot is in BOOTSTRAP_LADDER
        }

    The brief, the gauntlet's mint_budget step, the gauntlet's
    coverage_floor step, and the corpus-wide cadence tests all read
    this single helper. To change a story's policy, edit
    `BOOTSTRAP_LADDER` above (no other code change required).
    """
    row = BOOTSTRAP_LADDER.get(story_id)
    if row is not None:
        return {**row, "in_bootstrap": True}
    # Steady-state fallback (story 11+).
    return {
        "vocab_min":   MIN_NEW_WORDS_PER_STORY,   # = 3 (legacy v2.0 default)
        "vocab_max":   None,                       # no hard cap; brief surfaces a soft target
        "grammar_min": MIN_NEW_PER_WINDOW,         # = 1 (steady-state floor)
        "grammar_max": MAX_NEW_PER_STORY,          # = 1 (steady-state ceiling)
        "scene_class": None,                       # no scene constraint
        "in_bootstrap": False,
    }


def cadence_max_per_story(story_id: int) -> int:
    """Maximum legal number of new grammar introductions in this story.

    Reads the bootstrap ladder for stories 1..BOOTSTRAP_END; returns the
    steady-state `MAX_NEW_PER_STORY` (= 1) for stories 11+.
    """
    return ladder_for(story_id)["grammar_max"]


def cadence_min_per_story(story_id: int) -> int:
    """Minimum legal number of new grammar introductions in this story.

    The validator's coverage_floor step uses this to know whether the
    story has hit its grammar floor. Steady-state floor is 1 (when there
    are uncovered points in the active tier); bootstrap stories have
    explicit per-story floors per the ladder.
    """
    return ladder_for(story_id)["grammar_min"]


def cadence_window_for(story_id: int) -> tuple[int, int] | None:
    """
    Return the (lo, hi) inclusive story-id window that *ends* at story_id and
    is subject to the minimum-cadence rule. Returns None if the window falls
    inside or straddles the bootstrap region (where the rule does not apply).

    A window of CADENCE_WINDOW consecutive stories is only enforced once both
    its endpoints sit beyond BOOTSTRAP_END (= 10 under the v2.5 ladder).
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


# ── Tier coverage helpers ────────────────────────────────────────────────────
#
# Coverage = "for tier T, how many catalog points have intro_in_story set?"
# A tier is "uncovered" when at least one of its catalog entries has not
# yet appeared in any shipped story's `new_grammar` list.
#
# These helpers reconcile the two id namespaces:
#   * `data/grammar_catalog.json` — uses `N5_*` / `N4_*` ids.
#   * `data/grammar_state.json`   — uses internal `G0XX_*` ids that point
#     back to the catalog via the `catalog_id` field on each entry.
#
# A catalog point is "covered" iff some grammar_state entry has
# `catalog_id == <catalog point id>` AND `intro_in_story is not None`.
#
# Why this lives here (and not in agent_brief.py): both the validator
# (Check 3.9 / 3.10) and the brief need this; centralising avoids drift.


def _load_state_and_catalog() -> tuple[dict, dict]:
    """Load grammar_state and grammar_catalog from disk via _paths."""
    import json
    from _paths import DATA  # local import to avoid hard dep at import time
    state = json.loads((DATA / "grammar_state.json").read_text(encoding="utf-8"))
    catalog = json.loads((DATA / "grammar_catalog.json").read_text(encoding="utf-8"))
    return state, catalog


def coverage_status(
    state: dict | None = None,
    catalog: dict | None = None,
) -> dict:
    """Return per-tier coverage of the catalog by the current state.

    Output schema:
      {
        "by_jlpt": {
          "N5": {
             "total": 64,
             "covered": 10,
             "remaining": 54,
             "covered_ids":   ["N5_wa_topic", ...],
             "uncovered_ids": ["N5_dare_who", ...],
          },
          "N4": {...},
          ...
        },
        # gid_to_intro is a flat catalog_id → intro_in_story map for
        # quick lookups by callers that already know what they're after.
        "covered_catalog_ids": {"N5_wa_topic": 1, ...},
      }
    """
    if state is None or catalog is None:
        s, c = _load_state_and_catalog()
        state = state or s
        catalog = catalog or c

    # Build catalog_id → intro_in_story from state (a state entry's
    # `catalog_id` is the bridge; `intro_in_story` is what makes it covered).
    covered_cid_to_intro: dict[str, int] = {}
    for _gid, entry in (state.get("points") or {}).items():
        cid = entry.get("catalog_id")
        intro = entry.get("intro_in_story")
        if not cid or intro is None:
            continue
        # Earliest intro wins on duplicates (shouldn't happen, but be safe).
        if cid not in covered_cid_to_intro or covered_cid_to_intro[cid] > intro:
            covered_cid_to_intro[cid] = int(intro)

    by_jlpt: dict[str, dict] = {}
    for entry in catalog.get("entries", []):
        cid = entry["id"]
        jlpt = entry.get("jlpt") or "?"
        bucket = by_jlpt.setdefault(jlpt, {
            "total": 0,
            "covered": 0,
            "remaining": 0,
            "covered_ids": [],
            "uncovered_ids": [],
        })
        bucket["total"] += 1
        if cid in covered_cid_to_intro:
            bucket["covered"] += 1
            bucket["covered_ids"].append(cid)
        else:
            bucket["remaining"] += 1
            bucket["uncovered_ids"].append(cid)
    # Stable id order in each list
    for bucket in by_jlpt.values():
        bucket["covered_ids"].sort()
        bucket["uncovered_ids"].sort()
    return {
        "by_jlpt": by_jlpt,
        "covered_catalog_ids": covered_cid_to_intro,
    }


def uncovered_in_tier(
    jlpt_label: str,
    state: dict | None = None,
    catalog: dict | None = None,
) -> list[dict]:
    """Return the catalog entries (full dicts) that are NOT yet covered for the given JLPT label.

    Useful for the brief's `grammar_introduction_debt.recommended_for_this_story`.
    Sorted so that points whose prerequisites are ALREADY covered come first
    (a point is "ready" only when its prereqs are introduced).
    """
    if state is None or catalog is None:
        s, c = _load_state_and_catalog()
        state = state or s
        catalog = catalog or c

    cov = coverage_status(state=state, catalog=catalog)
    covered_cids = set(cov["covered_catalog_ids"].keys())
    out = []
    for entry in catalog.get("entries", []):
        if (entry.get("jlpt") or "?") != jlpt_label:
            continue
        cid = entry["id"]
        if cid in covered_cids:
            continue
        prereqs = entry.get("prerequisites") or []
        prereqs_satisfied = all(p in covered_cids for p in prereqs)
        out.append({
            **entry,
            "_prereqs_satisfied": prereqs_satisfied,
            "_unmet_prereqs": [p for p in prereqs if p not in covered_cids],
        })
    # Ready (prereqs satisfied) first, then by id for determinism.
    out.sort(key=lambda e: (not e["_prereqs_satisfied"], e["id"]))
    return out


# ── Recommendation ranking (leverage scoring) ───────────────────────────────
#
# The agent brief shows recommended grammar intros for the next story.
# Without ranking, the list is alphabetical and the agent (or a
# rushed human author) picks based on what reads first — which is
# usually a noisy choice. Worse, the foundational unblockers
# (te-form, mashita, masen, dictionary_form) sit deep in the
# alphabet next to one-shot interrogatives like 誰 / いつ.
#
# rank_uncovered() returns the prereq-ready uncovered points sorted by
# leverage. Higher score = pick first. The ranking is deterministic and
# explainable — every recommendation comes with a rationale showing
# which factors fired so the agent can sanity-check.
#
# Score components (additive):
#   * direct_unlocks: # of currently-uncovered points that have THIS
#     point as a direct prerequisite. Te-form unlocks 3 (te_iru,
#     te_kudasai, te_mo_ii); mashita unlocks 2 (ta_form,
#     masen_deshita); etc.
#   * paradigm_bonus: +5 for points that anchor an entire grammatical
#     paradigm (tense, negation, te-paradigm, copula split, adjective
#     class). Curated set; foundational shape, not popularity.
#   * earlier_tier_bonus: +20 if the point belongs to an earlier tier
#     than the current story's tier. Earlier-tier coverage is required
#     for tier advancement (Check 3.9), so any earlier-tier unlocked
#     point trumps current-tier picks.
#
# The brief surfaces the top 3 of the ranked list as the
# `recommended_for_this_story`, with the score breakdown as a
# `priority_rationale` field on each item.


# Manually curated "anchors a paradigm" set. Editing this list is the
# documented way to nudge future recommendations toward foundational
# coverage without rewriting the catalog. The bias of +5 was chosen
# so a paradigm-anchor with zero direct unlocks still outranks a
# leaf-node interrogative.
PARADIGM_ANCHORS: set[str] = {
    # Tense
    "N5_mashita",          # polite past — unlocks ta-form, past negative
    "N5_dictionary_form",  # plain non-past — unlocks attributive + plain paradigm
    # Negation
    "N5_masen",            # polite negative — unlocks nai-form, masenka, etc.
    # Te-paradigm
    "N5_te_form",          # verb te-form — unlocks te-iru, te-kudasai, te-mo-ii
    "N5_i_adj_te",         # i-adj te-form — unlocks adjective chaining
    # Copula / na-adjectives
    "N5_da",               # plain copula — required for casual writing
    "N5_na_adj",           # na-adjectives — unlocks descriptive predicates
    # Sentence-final / connectives
    "N5_kara_because",     # because-clause — most common reason connector
    "N5_ga_but",           # but-clause — most common contrast connector
    # Counters: arguably foundational because counted-nouns appear in
    # nearly every concrete scene; without them everything is "an X"
    # without a number.
    "N5_counters",
    # N4 paradigm anchors (for when we cross into N4 around story 11):
    "N4_te_iru",
    "N4_potential",
    "N4_passive",
    "N4_volitional",
    "N4_conditional_tara",
}


PARADIGM_BONUS_POINTS  = 5
EARLIER_TIER_BONUS     = 20


def rank_uncovered(
    state: dict | None = None,
    catalog: dict | None = None,
    target_story: int | None = None,
) -> list[dict]:
    """Rank ALL prereq-ready uncovered points by leverage score, descending.

    Returns a list of dicts with the catalog fields plus:
      * `_score`: total integer score
      * `_score_breakdown`: dict of contributing factors → points
      * `_unlocks`: list of catalog ids this point would directly unlock
      * `_paradigm_anchor`: True if in PARADIGM_ANCHORS
      * `_earlier_tier`: True if from a tier earlier than target_story's tier

    target_story is optional; if None, the earlier-tier bonus is skipped
    (the function then returns a globally-ranked list useful for offline
    inspection). The brief always passes target_story.
    """
    if state is None or catalog is None:
        s, c = _load_state_and_catalog()
        state = state or s
        catalog = catalog or c

    cov = coverage_status(state=state, catalog=catalog)
    covered_cids = set(cov["covered_catalog_ids"].keys())

    # Build prereq → list-of-dependents from the FULL catalog. We count
    # a point as a "dependent" only if it is also currently uncovered;
    # already-covered points don't need unlocking.
    dependents: dict[str, list[str]] = {}
    for entry in catalog.get("entries", []):
        if entry["id"] in covered_cids:
            continue
        for prereq in entry.get("prerequisites") or []:
            dependents.setdefault(prereq, []).append(entry["id"])

    # Determine target story's tier (used for earlier-tier bonus).
    target_jlpt = active_jlpt(target_story) if target_story is not None else None
    target_tier = JLPT_TO_TIER.get(target_jlpt, 99) if target_jlpt else 99

    ranked: list[dict] = []
    for entry in catalog.get("entries", []):
        cid = entry["id"]
        if cid in covered_cids:
            continue
        prereqs = entry.get("prerequisites") or []
        if not all(p in covered_cids for p in prereqs):
            continue  # not prereq-ready

        unlocks = sorted(dependents.get(cid, []))
        direct_unlocks = len(unlocks)

        is_paradigm = cid in PARADIGM_ANCHORS
        paradigm_pts = PARADIGM_BONUS_POINTS if is_paradigm else 0

        entry_jlpt = entry.get("jlpt")
        entry_tier = JLPT_TO_TIER.get(entry_jlpt, 99) if entry_jlpt else 99
        is_earlier_tier = (target_tier < 99 and entry_tier < target_tier)
        earlier_pts = EARLIER_TIER_BONUS if is_earlier_tier else 0

        score = direct_unlocks + paradigm_pts + earlier_pts
        ranked.append({
            **entry,
            "_score": score,
            "_score_breakdown": {
                "direct_unlocks":     direct_unlocks,
                "paradigm_bonus":     paradigm_pts,
                "earlier_tier_bonus": earlier_pts,
            },
            "_unlocks": unlocks,
            "_paradigm_anchor": is_paradigm,
            "_earlier_tier":    is_earlier_tier,
        })

    # Higher score first; ties broken by id for determinism (so that
    # repeated invocations produce identical brief output).
    ranked.sort(key=lambda e: (-e["_score"], e["id"]))
    return ranked


def tier_coverage_complete(
    jlpt_label: str,
    state: dict | None = None,
    catalog: dict | None = None,
) -> bool:
    """True iff every catalog entry tagged with `jlpt_label` is covered."""
    cov = coverage_status(state=state, catalog=catalog)
    return cov["by_jlpt"].get(jlpt_label, {"remaining": 0})["remaining"] == 0


if __name__ == "__main__":
    show_curve()
    print()
    print("── per-story tier ──")
    for sid in [1, 5, 10, 11, 15, 25, 26, 50, 51]:
        print(f"  story {sid:>3}: tier {active_tier(sid)} ({active_jlpt(sid)})")
    print()
    print("── catalog coverage ──")
    try:
        cov = coverage_status()
        for jlpt in ("N5", "N4", "N3", "N2", "N1", "?"):
            b = cov["by_jlpt"].get(jlpt)
            if not b:
                continue
            print(f"  {jlpt}: covered {b['covered']:3d}/{b['total']:3d}  "
                  f"remaining {b['remaining']:3d}")
    except Exception as e:  # pragma: no cover — defensive when run outside repo
        print(f"  (could not load state/catalog: {e})")
