#!/usr/bin/env python3
"""Single JSON payload of everything the LLM author agent needs.

This is the load-bearing tool of the v2 agentic-author architecture (per
`docs/v2-strategy-2026-04-27.md` §B3.7 and `docs/phase3-tasks-2026-04-28.md`
Task 1.9). The agent has no episodic memory between sessions; the brief IS
its memory. Without this tool the agent reasons from scratch every prompt
and the corpus drifts.

The brief is a strict superset of:
  * size band + content-token target for the next story
  * mint_budget — advisory cap on new words for this story
  * grouped, debt-starred word palette (from palette.py)
  * available grammar points
  * grammar_reinforcement_debt — every grammar point intro'd in the
    last W stories that still needs a reinforcement use; flagged
    `must_reinforce` when the target story is the last chance
  * north-star sentences for the era (stub until north_star.py lands)
  * scene coverage (stub until coverage.py lands)
  * echo warnings — top reused sentence shapes (stub until echo.py lands)
  * reinforcement debt (critical / due) — derived from the palette stars
  * lint rules active, with one-line summaries
  * anti-patterns to avoid (the audit's defects + escape examples)
  * one-line summary of the previous 3 stories so the agent doesn't
    continue a motif blindly
  * previous_closers — the literal JP closer of the last 3 stories so
    the agent doesn't accidentally clone a closing pattern

Usage
-----
  agent_brief.py 11                 # full brief for story 11 (JSON to stdout)
  agent_brief.py next               # same, for max(story_id) + 1
  agent_brief.py 11 --pretty        # pretty-printed JSON, easier to skim
  agent_brief.py 11 --section palette  # just one section
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from _common import iter_stories, load_grammar, load_vocab, parse_id_arg  # noqa: E402

# Import sibling tool modules.
import palette as _palette  # noqa: E402

# Reinforcement constants — must match `pipeline/grammar_progression.py`.
# A grammar point introduced in story N must reappear in
# ≥ MIN_REINFORCEMENT_USES of stories [N+1, N+REINFORCEMENT_WINDOW].
# We import lazily so the module loads cleanly even outside the venv.
try:
    from grammar_progression import (  # noqa: E402
        REINFORCEMENT_WINDOW as _REINFORCEMENT_WINDOW,
        MIN_REINFORCEMENT_USES as _MIN_REINFORCEMENT_USES,
    )
except Exception:  # pragma: no cover — defensive
    _REINFORCEMENT_WINDOW = 5
    _MIN_REINFORCEMENT_USES = 1


# ── Static knowledge that ships with the brief ───────────────────────────────
#
# The lint-rule summaries below MUST track `pipeline/semantic_lint.py`. When
# a new rule is added, add a line here. The point is to give the agent a
# one-screen view of every constraint it operates under.

_LINT_RULES_ACTIVE: list[dict] = [
    {"id": "11.1", "name": "inanimate-quiet",
     "summary": "Inanimate objects (book/letter/egg/chair) cannot be 静か です."},
    {"id": "11.2", "name": "consumption-target",
     "summary": "Verbs of eating/drinking need a consumable object."},
    {"id": "11.3", "name": "self-known-fact",
     "summary": "Don't 〜と思います about a fact the narrator already knows."},
    {"id": "11.4", "name": "companion-to",
     "summary": "Animate-companion と must not be misread as location-list と."},
    {"id": "11.5", "name": "redundant-mo",
     "summary": "も must add to a real, prior set; not just decorate."},
    {"id": "11.6", "name": "location-wo",
     "summary": "を with multiple noun-list locations is not a traversal."},
    {"id": "11.7", "name": "closer-noun-pile (NEW v2)",
     "summary": "Closer cannot be N や/と N、Adj N です with no verb. "
                "Use an action / dialogue / single concrete observation."},
    {"id": "11.8", "name": "tautological-equivalence (NEW v2)",
     "summary": "AのY は BのY です — same Y on both sides — is empty. "
                "Use a concrete adjective or comparison with NEW content."},
    {"id": "11.9", "name": "bare-known-fact-extended (NEW v2)",
     "summary": "〜と思います cannot embed universal pairings "
                "(夏は暑い, 夜は暗い)."},
    {"id": "11.10", "name": "inanimate-quiet-adverbial (NEW v2)",
     "summary": "Inanimate objects cannot act 静かに either — same defect "
                "as 11.1, adverbial form."},
]

_ANTI_PATTERNS: list[dict] = [
    {
        "name": "tautological-equivalence",
        "bad": "「猫の色は、雨の色です。」 (cat's color is rain's color)",
        "fix": "Use a concrete adjective: 「猫は白いです。」 OR add new content: "
               "「猫の色は雨より明るいです。」",
    },
    {
        "name": "closer-noun-pile",
        "bad": "「雨の朝、猫や花、静かな窓です。」",
        "fix": "End with an action or dialogue: 「猫は私のそばで寝ます。」 OR "
               "「友達は『ありがとう』と言います。」",
    },
    {
        "name": "bare-known-fact",
        "bad": "「夏は暑いと思います。」 (said in summer)",
        "fix": "Plain assertion: 「夏は暑いです。」 OR hedge something genuinely "
               "uncertain: 「友達は元気だと思います。」",
    },
    {
        "name": "misapplied-quiet",
        "bad": "「本は静かです。」 / 「本は静かにあります。」",
        "fix": "Reserve 静か for places (rooms, gardens, streets) and animate "
               "subjects (the cat is quiet). For inanimate objects, pick a "
               "different attribute: 「本は古いです。」 / 「本は明るい色です。」",
    },
    {
        "name": "decorative-noun",
        "bad": "Introducing 風 in s1, never echoing it. Reads as set-dressing.",
        "fix": "Every scene noun should appear in ≥2 sentences OR resolve "
               "into an action by the closer. If you need only one mention, "
               "make it part of a verb phrase, not a bare predicate.",
    },
]


# ── Stubs for not-yet-implemented tools ──────────────────────────────────────
#
# These return placeholders the agent can read without crashing. When the
# real tool lands (echo.py, coverage.py, north_star.py), wire it in and
# delete the stub.

def _echo_warnings_stub(target_story: int) -> dict:
    """Returns 'not implemented yet' instead of breaking the brief."""
    return {
        "implemented": False,
        "note": (
            "echo.py is not yet built (Phase 3a Task 1.5). When implemented, "
            "this section will list the top 20 most-reused sentence SHAPES "
            "across the corpus so the agent can avoid extending the "
            "rain-cat-window cycle. Until then: assume the corpus has "
            "over-used 「<X>は窓から私を見ます」 / 「<X>は静かです」 patterns "
            "and prefer fresh sentence shapes."
        ),
        "default_avoid_shapes": [
            "<X>は窓から私を見ます",
            "<X>は静かです",
            "<scene-noun>です。<scene-noun>です。",
            "<X>のYは<Z>のYです",  # caught by lint 11.8 anyway
            "<N>や<N>、<Adj><N>です",  # caught by lint 11.7 anyway
        ],
    }


def _scene_coverage_stub(target_story: int) -> dict:
    return {
        "implemented": False,
        "note": (
            "coverage.py is not yet built (Phase 3a Task 1.6). Until then, "
            "the agent should diversify: avoid stories that take place "
            "during 'morning at home' or 'rainy window observation' unless "
            "the previous 5 stories did NOT use that scene type."
        ),
    }


def _north_stars_stub(target_story: int) -> list[dict]:
    """Returns the v1 north-stars hand-drafted in v2-strategy-2026-04-27.md
    §1.5. When `data/north_stars.json` exists, replace this with a real load."""
    drafts = [
        (1, "「窓の外で、雨が木を濡らします。」",
         "Concrete subject + action; no pathetic fallacy needed."),
        (2, "「友達と公園を歩きます。小さい花があります。」",
         "Walking *with* someone; named smallness instead of vague 'quiet'."),
        (3, "「机の下に、卵があります。」",
         "Spatial anchor (under the desk); a concrete found object."),
        (4, "「ドアの上に、赤い花があります。」",
         "Named color above a doorway — eliminates color-equivalence."),
        (5, "「犬は椅子に座ります。」",
         "First sit-down; physical action by a non-narrator."),
        (6, "「猫は窓のそばにいます。私はペンを置いて、手紙を書きます。」",
         "Two grounded actions in one beat; cat exists in space, not as metaphor."),
        (7, "「月は白いです。星も白いです。」",
         "Direct color description — replaces moon's-color = star's-color tautology."),
        (8, "「夜の窓は明るいです。私は本を読みます。」",
         "A night that is bright, not just quiet."),
        (9, "「猫は私のそばで寝ています。私は本を持ちます。」",
         "Two beings, one room, both doing something concrete."),
        (10, "「友達は『元気ですか』と言います。」",
         "Dialogue arrives. From here, 思います is for genuine inference only."),
    ]
    # Era = the row whose story_id is closest to but not greater than target.
    era_entries = [(i, jp, note) for (i, jp, note) in drafts if i <= target_story]
    if not era_entries:
        # target_story < 1 or the target precedes the first north-star
        era_entries = drafts[:1]
    return [
        {"story_id": i, "north_star_jp": jp, "voice_note": note}
        for (i, jp, note) in era_entries[-3:]  # last 3 north-stars in the era
    ]


# ── Real composers ───────────────────────────────────────────────────────────

def _size_band_for(story_id: int) -> dict:
    """v1 norms; replace with progression.py call when v2 ladder lands."""
    # From `pipeline/progression.py`'s pattern: gentle ramp.
    if story_id <= 5:
        return {"sentences": [4, 7], "content_tokens": [14, 26], "target": 18}
    if story_id <= 10:
        return {"sentences": [6, 9], "content_tokens": [22, 36], "target": 28}
    if story_id <= 25:
        return {"sentences": [7, 11], "content_tokens": [28, 48], "target": 36}
    return {"sentences": [9, 16], "content_tokens": [36, 70], "target": 48}


def _previous_3_stories_summary(target_story: int) -> list[dict]:
    """One-line summary of the last 3 shipped stories before target_story."""
    out = []
    all_stories = [(sid, st) for sid, st in iter_stories() if sid < target_story]
    for sid, story in all_stories[-3:]:
        title_jp = (story.get("title") or {}).get("jp") or ""
        title_en = (story.get("title") or {}).get("en") or ""
        # Anchor object = most-frequent content noun.
        from collections import Counter
        nouns = Counter(
            tok.get("t") for sent in story.get("sentences", [])
            for tok in sent.get("tokens", [])
            if tok.get("role") == "content" and tok.get("word_id")
        )
        anchor = nouns.most_common(1)[0][0] if nouns else None
        out.append({
            "story_id": sid,
            "title_jp": title_jp,
            "title_en": title_en,
            "anchor_object": anchor,
            "sentence_count": len(story.get("sentences") or []),
        })
    return out


def _reinforcement_debt_from_palette(palette_json: dict) -> dict:
    critical = []
    due = []
    for cat, entries in palette_json.get("categories", {}).items():
        for e in entries:
            if e["star"] == "★★":
                critical.append({"word_id": e["word_id"], "lemma": e["lemma"],
                                 "category": cat, "last_use": e["last_use"]})
            elif e["star"] == "★":
                due.append({"word_id": e["word_id"], "lemma": e["lemma"],
                            "category": cat, "last_use": e["last_use"]})
    return {"critical": critical, "due": due}


def _grammar_reinforcement_debt(target_story: int) -> dict:
    """The single most load-bearing field for "ship in one go".

    For every grammar point introduced in stories [target-W, target-1] that
    has not yet hit MIN_REINFORCEMENT_USES inside its REINFORCEMENT_WINDOW,
    report:
      * grammar_id, label
      * intro_in_story
      * hits_in_window — how many follow-ups already reinforced it
      * still_needed   — max(0, MIN_REINFORCEMENT_USES - hits)
      * window_end     — the last story in which a reinforcement still counts
      * must_reinforce — TRUE iff target_story is the LAST chance to land
                         the grammar point inside its window. The author MUST
                         use it or the pedagogical-sanity test will go red.
      * should_reinforce — TRUE iff still_needed > 0 but there are future
                         windows to make it up. Strong nudge.
      * example         — a sample sentence surface from the intro story
                         that uses the point (so the author has a concrete
                         construction to echo, not just a grammar id).

    Sorted: must_reinforce first, then should_reinforce, then by intro story.
    """
    grammar = load_grammar()
    stories_by_id: dict[int, dict] = dict(iter_stories())

    # Build per-story usage map (which grammar_ids appear in story N) AND
    # the per-story intros list (from the story's `new_grammar` field —
    # the same source the pedagogical-sanity test consults).
    used: dict[int, set[str]] = {}
    intros_by_story: dict[int, list[str]] = {}
    intro_story_for_gid: dict[str, int] = {}
    intro_examples: dict[str, tuple[int, str]] = {}  # gid -> (story_id, surface)
    for sid, story in stories_by_id.items():
        u: set[str] = set()
        for sent in story.get("sentences", []):
            tokens = sent.get("tokens", [])
            sentence_gids: set[str] = set()
            for tok in tokens:
                for gid in (tok.get("grammar_id"),
                            (tok.get("inflection") or {}).get("grammar_id")):
                    if gid:
                        u.add(gid)
                        sentence_gids.add(gid)
            for gid in sentence_gids:
                if gid not in intro_examples or intro_examples[gid][0] > sid:
                    surface = "".join(t.get("t", "") for t in tokens)
                    intro_examples[gid] = (sid, surface)
        used[sid] = u

        # Story-declared intros (same source as test_introduced_grammar_is_reinforced)
        ng = story.get("new_grammar") or []
        ids: list[str] = []
        for x in ng:
            if isinstance(x, str):
                ids.append(x)
            elif isinstance(x, dict):
                for k in ("id", "grammar_id", "catalog_id"):
                    if k in x:
                        ids.append(x[k])
                        break
        intros_by_story[sid] = ids
        for gid in ids:
            # Earliest story that declares gid in new_grammar wins.
            if gid not in intro_story_for_gid or intro_story_for_gid[gid] > sid:
                intro_story_for_gid[gid] = sid

    out: list[dict] = []
    for gid, intro in intro_story_for_gid.items():
        p = grammar.get("points", {}).get(gid, {})
        # Only points introduced *strictly before* the target story can have
        # debt against the target story (the target story is the place to pay).
        if intro >= target_story:
            continue
        window_end = intro + _REINFORCEMENT_WINDOW
        # No more debt to pay if we're already past the window (can't be fixed
        # by the target story).
        if target_story > window_end:
            continue
        # Count hits in [intro+1 .. min(window_end, target-1)] — i.e. only
        # what's already shipped.
        followups = [i for i in range(intro + 1, target_story)
                     if i in stories_by_id]
        hits_in_window = sum(1 for i in followups if gid in used.get(i, set()))
        still_needed = max(0, _MIN_REINFORCEMENT_USES - hits_in_window)
        if still_needed == 0:
            continue  # already satisfied; not debt
        # `must_reinforce` semantics — when must this story carry the point?
        #
        # Two ways for the test to fire if THIS story doesn't reinforce:
        #   A. Window is closing: target_story == window_end (no future
        #      stories in the window will get a chance to pay the debt).
        #   B. Pedagogical-sanity test runs `min(MIN_USES, len(followups))`
        #      where followups = currently-shipped stories in window. If
        #      target_story is the only currently-shipped follow-up, then
        #      shipping it without the point makes the test go red NOW —
        #      regardless of how many future windows remain in principle.
        #      That's the trap that bit story 3.
        must = (
            target_story == window_end
            or len(followups) == 0  # no shipped story has reinforced yet,
                                     # and target is the next one shipping
        )
        sample_sid, sample_surface = intro_examples.get(gid, (intro, ""))
        out.append({
            "grammar_id": gid,
            "label": p.get("label") or p.get("name") or gid,
            "intro_in_story": intro,
            "window_end": window_end,
            "hits_in_window": hits_in_window,
            "still_needed": still_needed,
            "must_reinforce": must,
            "should_reinforce": not must,
            "example": {
                "from_story": sample_sid,
                "surface": sample_surface,
            },
        })

    out.sort(key=lambda e: (
        not e["must_reinforce"],          # musts first
        not e["should_reinforce"],        # then shoulds
        e["intro_in_story"],              # then by intro order
    ))
    return {
        "policy": {
            "window": _REINFORCEMENT_WINDOW,
            "min_uses": _MIN_REINFORCEMENT_USES,
            "rule": (
                "A grammar point introduced in story N must reappear in at "
                f"least {_MIN_REINFORCEMENT_USES} of stories "
                f"[N+1, N+{_REINFORCEMENT_WINDOW}]. `must_reinforce: true` "
                "means THIS story is the last chance — author it in or the "
                "pedagogical-sanity test will fail."
            ),
        },
        "must_reinforce_count": sum(1 for e in out if e["must_reinforce"]),
        "should_reinforce_count": sum(1 for e in out if e["should_reinforce"]),
        "items": out,
    }


def _grammar_introduction_debt(target_story: int) -> dict:
    """Tell the agent which N-tier grammar points are still uncovered.

    Until every catalog point in the *current tier* (and all earlier tiers)
    has an `intro_in_story`, every post-bootstrap story MUST introduce at
    least one new grammar point. The validator's Check 3.10 enforces this;
    this section gives the agent the menu and a recommended pick.

    Output schema:
      {
        "policy": {...},
        "current_jlpt": "N5",
        "current_tier_window": [1, 10],
        "must_introduce": True/False,
        "must_introduce_reasons": [...],
        "coverage_summary": {"N5": {"covered": 10, "total": 54, "remaining": 44}, ...},
        "uncovered_in_current_tier": [<catalog entries, prereqs-ready-first>],
        "earlier_uncovered": [...],          # earlier-tier points still uncovered
        "recommended_for_this_story": [<top 3 ready picks with examples>]
      }
    """
    try:
        from grammar_progression import (  # noqa: E402
            active_jlpt,
            BOOTSTRAP_END,
            TIER_WINDOWS,
            coverage_status,
            uncovered_in_tier,
            JLPT_TO_TIER,
        )
    except Exception:  # pragma: no cover — defensive
        return {
            "implemented": False,
            "note": "grammar_progression coverage helpers unavailable",
        }

    cov = coverage_status()
    current_jlpt = active_jlpt(target_story)
    current_tier = JLPT_TO_TIER.get(current_jlpt, 1)
    tier_window = next(
        ([lo, hi] for t, lo, hi, _ in TIER_WINDOWS if t == current_tier),
        [1, 10],
    )

    # Coverage summary across every tier — collapses our "covered_ids" /
    # "uncovered_ids" lists down to scalar counts for at-a-glance reading.
    coverage_summary = {
        jlpt: {"covered": b["covered"],
               "total":   b["total"],
               "remaining": b["remaining"]}
        for jlpt, b in cov["by_jlpt"].items()
    }

    # Earlier-tier uncovered (these are URGENT — they should never have been
    # skipped; the gauntlet's tier-coverage-gate forbids advancing past them).
    earlier_uncovered: list[dict] = []
    for t, _lo, _hi, jlpt in TIER_WINDOWS:
        if t >= current_tier:
            continue
        for entry in uncovered_in_tier(jlpt):
            earlier_uncovered.append({
                "catalog_id": entry["id"],
                "jlpt": entry.get("jlpt"),
                "title": entry.get("title"),
                "short": entry.get("short"),
                "prereqs_satisfied": entry["_prereqs_satisfied"],
                "unmet_prereqs": entry["_unmet_prereqs"],
            })

    # Current tier uncovered, prereq-ready first.
    cur_uncov_full = uncovered_in_tier(current_jlpt)
    uncovered_in_current_tier = [
        {
            "catalog_id": e["id"],
            "jlpt": e.get("jlpt"),
            "title": e.get("title"),
            "short": e.get("short"),
            "examples": e.get("examples") or [],
            "prereqs_satisfied": e["_prereqs_satisfied"],
            "unmet_prereqs": e["_unmet_prereqs"],
        }
        for e in cur_uncov_full
    ]

    # Recommended picks: top 3 prereq-ready entries from the current tier
    # (or earlier tiers, which are even more urgent).
    candidate_pool = []
    candidate_pool.extend(
        e for e in earlier_uncovered if e["prereqs_satisfied"]
    )
    candidate_pool.extend(
        e for e in uncovered_in_current_tier if e["prereqs_satisfied"]
    )
    recommended = candidate_pool[:3]

    # Decide must_introduce.
    must = False
    reasons = []
    if target_story > BOOTSTRAP_END:
        if any(b["remaining"] > 0
               for jlpt, b in coverage_summary.items()
               if JLPT_TO_TIER.get(jlpt, 99) <= current_tier):
            must = True
            reasons.append(
                f"current tier {current_jlpt} has uncovered points; "
                "every post-bootstrap story must introduce ≥1 grammar point "
                "while uncovered points remain in current or earlier tiers."
            )
    else:
        # Bootstrap — soft nudge, not hard requirement (cap policed elsewhere).
        if uncovered_in_current_tier:
            reasons.append(
                f"bootstrap window: cap {15} aggregate intros across "
                f"stories 1..{BOOTSTRAP_END}, but try to keep the foundational "
                "set well-distributed."
            )

    return {
        "policy": {
            "rule": (
                "Every post-bootstrap story must introduce at least one new "
                "grammar point until the current tier (and all earlier tiers) "
                "have been fully covered. The current tier is JLPT-determined "
                "by story_id (see grammar_progression.TIER_WINDOWS). The "
                "validator's Check 3.10 hard-blocks the build if this is "
                "violated; the gauntlet's `coverage_floor` step blocks the "
                "ship."
            ),
            "advancement": (
                "A story whose tier is higher than the previous story's tier "
                "may only ship if every catalog point in the previous tier "
                "has `intro_in_story` set (Check 3.9 tier-coverage-gate)."
            ),
            "bootstrap_end": BOOTSTRAP_END,
        },
        "current_jlpt": current_jlpt,
        "current_tier_window": tier_window,
        "must_introduce": must,
        "must_introduce_reasons": reasons,
        "coverage_summary": coverage_summary,
        "uncovered_in_current_tier": uncovered_in_current_tier,
        "earlier_uncovered": earlier_uncovered,
        "recommended_for_this_story": recommended,
    }


def _previous_closers(target_story: int, n: int = 3) -> list[dict]:
    """The literal JP closer of the last n stories.

    Used to surface "don't end with X again" without making the agent open
    every story file. The closer is defined as the last sentence; if the
    spec carries a `role: closer` we prefer that.
    """
    out: list[dict] = []
    all_stories = [(sid, st) for sid, st in iter_stories() if sid < target_story]
    for sid, story in all_stories[-n:]:
        sentences = story.get("sentences") or []
        if not sentences:
            continue
        # Prefer an explicit closer role; fall back to last sentence.
        closer = next(
            (s for s in reversed(sentences) if s.get("role") == "closer"),
            sentences[-1],
        )
        surface = "".join(t.get("t", "") for t in closer.get("tokens", []))
        out.append({
            "story_id": sid,
            "closer_jp": surface,
            "closer_en": closer.get("en", ""),
        })
    return out


def _mint_budget_for(target_story: int) -> dict:
    """Default per-story mint budget, per the monogatari-author skill §C.

    These are advisory caps the author should respect; `would-mint` reports
    against them and the gauntlet's mint-budget step (when wired) enforces.

    Defaults:
      story 1:           10–16 (cold start)
      stories 2–5:        2–5
      stories 6–15:       1–4
      stories 16+:        0–3
    """
    if target_story <= 1:
        lo, hi = 10, 16
        rationale = "cold start — needs the founding word ladder"
    elif target_story <= 5:
        lo, hi = 2, 5
        rationale = "early ramp — small coherent neighborhoods only"
    elif target_story <= 15:
        lo, hi = 1, 4
        rationale = "establishment phase — corpus is still thin"
    else:
        lo, hi = 0, 3
        rationale = "consolidation — prefer reinforcement over expansion"
    return {
        "min": lo,
        "max": hi,
        "target": (lo + hi) // 2,
        "rationale": rationale,
        "enforcement": (
            "HARD BLOCK at the gauntlet's `mint_budget` step: "
            "exceeding `max` fails dry-run AND ship. Use `would-mint` "
            "per candidate sentence to keep a running count; if you "
            "must exceed the cap, document the expansion in the spec's "
            "`intent` field and stop to ask the user."
        ),
    }


# ── Public entry point ──────────────────────────────────────────────────────

def build_brief(target_story: int) -> dict[str, Any]:
    palette_json = _palette.build_palette(target_story)
    grammar_palette = _palette.build_grammar_palette(target_story)
    return {
        "story_id": target_story,
        "size_band": _size_band_for(target_story),
        "mint_budget": _mint_budget_for(target_story),
        "palette": palette_json,
        "grammar_points": grammar_palette,
        "grammar_introduction_debt": _grammar_introduction_debt(target_story),
        "grammar_reinforcement_debt": _grammar_reinforcement_debt(target_story),
        "north_stars": _north_stars_stub(target_story),
        "scene_coverage": _scene_coverage_stub(target_story),
        "echo_warnings": _echo_warnings_stub(target_story),
        "reinforcement_debt": _reinforcement_debt_from_palette(palette_json),
        "lint_rules_active": _LINT_RULES_ACTIVE,
        "anti_patterns_to_avoid": _ANTI_PATTERNS,
        "previous_3_stories": _previous_3_stories_summary(target_story),
        "previous_closers": _previous_closers(target_story),
        "schema_version": "2026-04-29",
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def _next_story_id() -> int:
    last = max((sid for sid, _ in iter_stories()), default=0)
    return last + 1


def _parse_target(arg: str) -> int:
    if arg == "next":
        return _next_story_id()
    return parse_id_arg(arg)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("target", help="story id, 'story_N', or 'next'")
    p.add_argument("--pretty", action="store_true",
                   help="indent JSON for human reading")
    p.add_argument("--section",
                   help="emit a single top-level section instead of the full brief")
    args = p.parse_args()

    target = _parse_target(args.target)
    brief = build_brief(target)
    if args.section:
        if args.section not in brief:
            print(f"Unknown section '{args.section}'. Available: "
                  f"{', '.join(brief.keys())}", file=sys.stderr)
            sys.exit(2)
        payload = brief[args.section]
    else:
        payload = brief

    indent = 2 if args.pretty else None
    print(json.dumps(payload, ensure_ascii=False, indent=indent))


if __name__ == "__main__":
    main()
