#!/usr/bin/env python3
"""Single JSON payload of everything the LLM author agent needs.

This is the load-bearing tool of the v2 agentic-author architecture (per
`docs/archive/v2-strategy-2026-04-27.md` §B3.7 and `docs/archive/phase3-tasks-2026-04-28.md`
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

from _common import iter_stories, load_grammar, load_vocab_attributed, parse_id_arg  # noqa: E402

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
    """Returns the v1 north-stars hand-drafted in docs/archive/v2-strategy-2026-04-27.md
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


def _vocab_reinforcement_debt(target_story: int) -> dict:
    """Words intro'd in the last VOCAB_REINFORCE_WINDOW stories that still
    need a follow-up use, classified by urgency.

    The post-ship test `test_vocab_words_are_reinforced` (Rule R1) fails
    if a word intro'd in story N doesn't reappear in ≥1 of the next
    VOCAB_REINFORCE_WINDOW=10 stories. R1 ALSO exempts bootstrap stories
    entirely (`if n <= BOOTSTRAP_END: continue`) — words minted during
    the bootstrap front-load aren't policed by R1 at all.

    This function surfaces reinforcement debt to the brief WITHOUT
    over-enforcing it. Concretely:

      * `must_reinforce=True` is reserved for the LAST guaranteed slot —
        i.e. when the R1 window is about to close on the word and no
        follow-up has used it yet. That is `target_story == intro_story
        + VOCAB_REINFORCE_WINDOW`. Older code marked this on the very
        next story after intro (`target_story == intro_story + 1`),
        which forced every follow-up to recycle every word from the
        previous story — directly contradicting R1's "≥1 in the next 10"
        spec and making bootstrap follow-up stories impossible to ship
        when the prior story was a wide front-load (story 1 mints
        ~14–18 words; story 2 cannot honestly use them all).

      * Words intro'd in bootstrap stories (intro_story <= BOOTSTRAP_END)
        NEVER become `must_reinforce`. They mirror R1's exemption: the
        bootstrap is calibrated to seed broadly, with the corpus-wide
        natural reuse curve doing the reinforcement, not a per-story
        bottleneck. They CAN appear as `should_reinforce` so the agent
        sees "due soon" hints.

      * All other in-window-but-not-last-slot words are
        `should_reinforce=True` — informational, non-blocking. The
        gauntlet's `step_vocab_reinforcement` only hard-blocks on
        `must_reinforce`.

    Output schema:
      {
        "window": 10,
        "min_uses": 1,
        "must_reinforce_count": int,    # words at their last-chance slot
        "items": [
          {
            "word_id": "W00038",
            "lemma": "箱",
            "intro_in_story": 7,
            "stories_since_intro": 1,
            "must_reinforce": True/False,
            "should_reinforce": True/False,
          }, ...
        ]
      }

    History (2026-04-29): the original implementation flagged every word
    minted in the immediately previous story as must_reinforce for THIS
    story. That created an absurd bottleneck after wide-mint slots
    (story 1 minted 18 words → story 2 was required to use all 18 or
    fail to ship). Relaxed to "last slot in the R1 window" + bootstrap
    exemption, matching R1's actual contract. See AGENTS.md and
    docs/archive/phase4-bootstrap-reload-2026-04-29.md for the discussion.
    """
    try:
        from grammar_progression import (  # noqa: E402
            VOCAB_REINFORCE_WINDOW,
            VOCAB_REINFORCE_MIN_USES,
            BOOTSTRAP_END,
        )
    except Exception:
        VOCAB_REINFORCE_WINDOW = 10
        VOCAB_REINFORCE_MIN_USES = 1
        BOOTSTRAP_END = 10

    # Build per-word usage map across all shipped stories.
    used_in: dict[str, set[int]] = {}
    intro_in: dict[str, int] = {}
    word_lemma: dict[str, str] = {}
    for sid, s in iter_stories():
        for sent in s.get("sentences", []):
            for tok in sent.get("tokens", []):
                wid = tok.get("word_id")
                if not wid:
                    continue
                used_in.setdefault(wid, set()).add(sid)

    try:
        vocab = load_vocab_attributed().get("words") or {}
    except Exception:
        vocab = {}
    for wid, w in vocab.items():
        fs = w.get("first_story")
        if isinstance(fs, str) and fs.startswith("story_"):
            try:
                intro_in[wid] = int(fs.split("_", 1)[1])
            except Exception:
                pass
        elif isinstance(fs, int):
            intro_in[wid] = fs
        word_lemma[wid] = w.get("surface") or wid

    items: list[dict] = []
    must_count = 0
    for wid, n in intro_in.items():
        if n >= target_story:
            continue            # word intro'd in this story or later — N/A
        # The R1 window for word intro'd at story n inspects stories
        # (n+1)..(n+VOCAB_REINFORCE_WINDOW). target_story is one of those
        # if n < target_story <= n + VOCAB_REINFORCE_WINDOW.
        if target_story - n > VOCAB_REINFORCE_WINDOW:
            continue            # window already closed; can't fix here
        # How many shipped follow-up stories used it?
        followups_shipped = [i for i in range(n + 1, target_story)
                             if i in used_in.get(wid, set())]
        if followups_shipped:
            continue            # already reinforced; no debt

        # No follow-up has used it yet. Decide whether THIS story is
        # forced to carry the reinforcement.
        #
        # Rule (relaxed 2026-04-29): mirror R1's actual contract.
        #
        #   1. R1 exempts bootstrap stories (intro_in_story <=
        #      BOOTSTRAP_END) entirely. Words minted during the
        #      bootstrap front-load are never "must" — the bootstrap
        #      caps are calibrated for breadth-of-seed, and natural
        #      reuse over the next 10+ stories handles reinforcement.
        #   2. For non-bootstrap intro stories, this story is "must"
        #      ONLY if the R1 window is about to close — i.e. this is
        #      the LAST follow-up slot (target_story == intro_story +
        #      VOCAB_REINFORCE_WINDOW). Earlier slots within the window
        #      are `should_reinforce` (informational, non-blocking).
        is_bootstrap_intro = (n <= BOOTSTRAP_END)
        is_last_window_slot = (target_story == n + VOCAB_REINFORCE_WINDOW)
        must = (not is_bootstrap_intro) and is_last_window_slot
        if must:
            must_count += 1
        items.append({
            "word_id": wid,
            "lemma":   word_lemma.get(wid, wid),
            "intro_in_story":      n,
            "stories_since_intro": target_story - n,
            "window_end":          n + VOCAB_REINFORCE_WINDOW,
            "must_reinforce":      must,
            "should_reinforce":    not must,
        })

    # Sort: must_reinforce first, then by intro recency (closer = more urgent).
    items.sort(key=lambda i: (0 if i["must_reinforce"] else 1,
                              -i["intro_in_story"]))
    return {
        "window":               VOCAB_REINFORCE_WINDOW,
        "min_uses":             VOCAB_REINFORCE_MIN_USES,
        "must_reinforce_count": must_count,
        "items":                items,
    }


def _r1_strict_required(target_story: int) -> dict:
    """Words this story is FORCED to carry to keep `test_vocab_words_are_reinforced`
    (Rule R1) green after live ship.

    The pytest evaluates R1 with the corpus AS-OF-NOW. For each prior
    post-bootstrap story `n` whose mints have fewer than
    `min(MIN_USES, len(followups))` shipped reuses, this story (which will
    become a new followup of every prior story whose intro fell within
    the last VOCAB_REINFORCE_WINDOW stories) MUST carry the missing word
    or the test fails immediately after ship.

    The existing `_vocab_reinforcement_debt` is intentionally permissive
    (only flags `must_reinforce` at the LAST R1 slot); that worked for
    the bootstrap front-load logic but allowed a subtle gap: when a
    PRIOR story's mints have only this story as their first available
    followup, the test counts `min(1, 1) = 1` and demands a hit — yet
    the brief said `must_reinforce: false` because we weren't at the
    last slot. Story 17 hit this trap (3 mints from story 16 needed
    by R1 immediately, brief said no, gauntlet shipped, pytest failed).
    This function closes the gap: it surfaces the test-equivalent
    "you MUST carry these or pytest will go red" set.

    Output schema:
      {
        "rule": "R1",
        "window": 10,
        "min_uses": 1,
        "items": [
          {
            "word_id": "W00099",
            "lemma": "ノート",
            "intro_in_story": 16,
            "shipped_followups_count": 0,   # before this story
            "shipped_hits": 0,
            "required_hits_after_this_ship": 1,
            "reason": "...",
          }, ...
        ],
      }

    The list is empty when nothing is forced; the gauntlet's
    `step_r1_strict` walks `items[].word_id` and hard-blocks any not
    present in the built story's tokens.
    """
    try:
        from grammar_progression import (  # noqa: E402
            VOCAB_REINFORCE_WINDOW,
            VOCAB_REINFORCE_MIN_USES,
            BOOTSTRAP_END,
        )
    except Exception:
        VOCAB_REINFORCE_WINDOW = 10
        VOCAB_REINFORCE_MIN_USES = 1
        BOOTSTRAP_END = 10

    # Build per-story usage map (already-shipped corpus only).
    used_in: dict[int, set[str]] = {}
    intros_by_story: dict[int, list[str]] = {}
    for sid, s in iter_stories():
        if sid >= target_story:
            continue
        used: set[str] = set()
        for sec in ("title",):
            for tok in (s.get(sec) or {}).get("tokens", []):
                wid = tok.get("word_id")
                if wid:
                    used.add(wid)
        for sent in s.get("sentences", []):
            for tok in sent.get("tokens", []):
                wid = tok.get("word_id")
                if wid:
                    used.add(wid)
        used_in[sid] = used
        # new_words on the shipped story drives intros (canonical source).
        ids = [w if isinstance(w, str) else w.get("id") or w.get("word_id", "")
               for w in (s.get("new_words") or [])]
        intros_by_story[sid] = [i for i in ids if i]

    # Walk lemma map for human-readable output.
    try:
        vocab = load_vocab_attributed().get("words") or {}
    except Exception:
        vocab = {}
    word_lemma: dict[str, str] = {wid: (w.get("surface") or wid)
                                  for wid, w in vocab.items()}

    items: list[dict] = []
    # For each prior post-bootstrap story whose R1 window still includes
    # `target_story`, evaluate R1 as the test would after this ship.
    for n, ids in intros_by_story.items():
        if n <= BOOTSTRAP_END:
            continue                # R1 exempts bootstrap intros
        if not ids:
            continue
        # The R1 followup window for story n is (n+1)..(n+W). target_story
        # is in this window iff n < target_story <= n+W. Outside the
        # window R1 doesn't care anyway.
        if target_story <= n or target_story > n + VOCAB_REINFORCE_WINDOW:
            continue

        # `followups_count_after_ship` = how many of (n+1..n+W) will exist
        # in the corpus once this story ships. Only stories already shipped
        # PLUS this one count.
        shipped_followup_ids = [i for i in range(n + 1, n + 1 + VOCAB_REINFORCE_WINDOW)
                                if i < target_story and i in used_in]
        followups_count_after_ship = len(shipped_followup_ids) + 1  # +1 for this story
        if followups_count_after_ship < VOCAB_REINFORCE_MIN_USES:
            continue                # window not yet judgable
        required = min(VOCAB_REINFORCE_MIN_USES, followups_count_after_ship)

        for wid in ids:
            shipped_hits = sum(1 for i in shipped_followup_ids
                               if wid in used_in.get(i, set()))
            if shipped_hits >= required:
                continue            # already satisfied by earlier ship(s)
            # This story MUST be one of the missing hits, otherwise R1
            # post-ship sees `len(hits) < required` and fails.
            items.append({
                "word_id":                       wid,
                "lemma":                         word_lemma.get(wid, wid),
                "intro_in_story":                n,
                "shipped_followups_count":       len(shipped_followup_ids),
                "shipped_hits":                  shipped_hits,
                "required_hits_after_this_ship": required,
                "reason":                        (
                    f"Story {n} mint {wid} has {shipped_hits} shipped "
                    f"reuse(s); after this ship the followup window will "
                    f"hold {followups_count_after_ship} stories, R1 needs "
                    f"≥{required}. Story {target_story} must carry it."
                ),
            })

    # Sort: oldest intro first (most at-risk in window), then by lemma.
    items.sort(key=lambda i: (i["intro_in_story"], i["lemma"]))
    return {
        "rule":     "R1",
        "window":   VOCAB_REINFORCE_WINDOW,
        "min_uses": VOCAB_REINFORCE_MIN_USES,
        "items":    items,
    }


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


def _ranking_explanation(r: dict) -> str:
    """One-line, human-readable why-this-was-ranked-here.

    Used in the compact brief so the agent isn't just told "pick this" —
    it's told why. Keeps the agent's autonomy: if the rationale doesn't
    match the story they want to write, they can pick #2 or #3 and
    document the deferral in the spec's `intent` field.
    """
    parts: list[str] = []
    n = r["_score_breakdown"]["direct_unlocks"]
    if n:
        sample = ", ".join((r.get("_unlocks") or [])[:3])
        parts.append(
            f"unlocks {n} downstream point(s) ({sample}{'…' if n > 3 else ''})"
        )
    if r.get("_paradigm_anchor"):
        parts.append("anchors a foundational paradigm")
    if r.get("_earlier_tier"):
        parts.append("earlier-tier — required for tier advancement (Check 3.9)")
    if not parts:
        parts.append("no special leverage; baseline coverage candidate")
    return "; ".join(parts) + f" (score {r['_score']})"


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
            rank_uncovered,
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

    # Recommended picks: top 3 prereq-ready entries by leverage score.
    # The ranking accounts for direct unlocks (how many uncovered points
    # have THIS as a prereq), a paradigm-anchor bonus for foundational
    # picks (te-form, mashita, masen, etc.), and an earlier-tier bonus
    # so any earlier-tier point trumps current-tier picks (Check 3.9
    # tier-advancement gate). See grammar_progression.rank_uncovered for
    # the scoring rationale. Replaces the previous alphabetic pool which
    # buried foundational picks next to leaf interrogatives.
    ranked = rank_uncovered(target_story=target_story)
    recommended = []
    for r in ranked[:3]:
        recommended.append({
            "catalog_id":   r["id"],
            "jlpt":         r.get("jlpt"),
            "title":        r.get("title"),
            "short":        r.get("short"),
            "examples":     r.get("examples") or [],
            "prereqs_satisfied": True,        # rank_uncovered guarantees this
            "unmet_prereqs":     [],
            "priority_score":     r["_score"],
            "priority_rationale": {
                "direct_unlocks":   r["_score_breakdown"]["direct_unlocks"],
                "unlocks":          r["_unlocks"],
                "paradigm_anchor":  r["_paradigm_anchor"],
                "earlier_tier":     r["_earlier_tier"],
                "explanation": _ranking_explanation(r),
            },
        })

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
    """Per-story mint budget, read from the v2.5 BOOTSTRAP_LADDER.

    Replaces the prior hand-coded defaults with a single source of
    truth: `pipeline/grammar_progression.BOOTSTRAP_LADDER`. The ladder
    has explicit per-story (vocab_min, vocab_max) bounds for stories
    1..BOOTSTRAP_END (= 10) tapering from a wide front-load to the
    steady-state policy by story 11. See
    `docs/archive/phase4-bootstrap-reload-2026-04-29.md` §3 for the table.
    """
    try:
        from grammar_progression import ladder_for  # noqa: E402
        ladder = ladder_for(target_story)
    except Exception:
        # Defensive fallback (matches the legacy steady-state defaults).
        ladder = {"vocab_min": 1, "vocab_max": 4, "in_bootstrap": False}
    lo = ladder["vocab_min"]
    hi = ladder["vocab_max"] if ladder["vocab_max"] is not None else lo + 2
    if ladder.get("in_bootstrap"):
        rationale = (
            f"bootstrap slot {target_story} of "
            f"{__import__('grammar_progression').BOOTSTRAP_END} — "
            f"front-loaded ladder per Phase 4 reload"
        )
    elif target_story <= 25:
        rationale = "establishment phase — corpus is still thin"
    else:
        rationale = "consolidation — prefer reinforcement over expansion"
    return {
        "min": lo,
        "max": hi,
        "target": (lo + hi) // 2,
        "in_bootstrap": ladder.get("in_bootstrap", False),
        "rationale": rationale,
        "enforcement": (
            "HARD BLOCK at the gauntlet's `mint_budget` step: "
            "minting outside [min, max] fails dry-run AND ship. "
            "Bootstrap slots ALSO enforce a min (the slot prescribes "
            "WHICH words to seed — see `must_hit.seed_plan`). "
            "Use `would-mint` per candidate sentence to keep a running "
            "count; if you must override the bounds, burn one of the "
            "session's §G overrides and document in the spec's `intent`."
        ),
    }


def _seed_plan_for_story(target_story: int) -> dict:
    """Read the prescriptive seed plan for `target_story` from
    `data/v2_5_seed_plan.json`.

    The seed plan is the bootstrap-window companion to the ladder:
    it prescribes which lemmas + grammar IDs each slot 1..10 must
    seed. The agent's brief surfaces this as `must_hit.seed_plan`
    and the gauntlet's mint_budget + coverage_floor steps enforce
    the count bounds; the lemma-identity prescription is enforced
    softly (logged as warning if a slot ships different lemmas).

    Returns an empty dict for stories outside the bootstrap window
    or when the file is absent (graceful degradation).
    """
    try:
        from _paths import DATA  # noqa: E402
    except Exception:
        return {}
    plan_path = DATA / "v2_5_seed_plan.json"
    if not plan_path.exists():
        return {}
    try:
        import json as _json
        plan = _json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return plan.get("stories", {}).get(str(target_story), {}) or {}


def _scene_affordances_for(scene_class: str | None) -> dict:
    """Read the noun palette for a scene from `data/scene_affordances.json`.

    Used by the brief to surface "the nouns that naturally live in
    this scene" so the agent doesn't have to guess (which is what
    produced "warm egg on a road"-class implausibilities in v2.0).
    """
    if not scene_class:
        return {}
    try:
        from _paths import DATA  # noqa: E402
    except Exception:
        return {}
    aff_path = DATA / "scene_affordances.json"
    if not aff_path.exists():
        return {}
    try:
        import json as _json
        aff = _json.loads(aff_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return aff.get("scenes", {}).get(scene_class, {})


def _compact_word(entry: dict, category: str | None = None) -> dict:
    """Keep only fields an author uses while drafting a sentence."""
    out = {
        "id": entry.get("word_id"),
        "jp": entry.get("lemma"),
        "pos": entry.get("pos"),
        "meaning": ", ".join((entry.get("meanings") or [])[:2]),
    }
    if category:
        out["category"] = category
    if entry.get("star"):
        out["debt"] = entry["star"]
    if entry.get("last_use") is not None:
        out["last_use"] = entry.get("last_use")
    return out


def _compact_palette(palette_json: dict, *, per_category: int = 6) -> dict:
    """Small author palette: debt words first, then enough nouns/verbs to draft."""
    categories = palette_json.get("categories") or {}
    by_category: dict[str, list[dict]] = {}
    debt_words: list[dict] = []
    for cat, entries in categories.items():
        ordered = sorted(
            entries,
            key=lambda e: (0 if e.get("star") else 1, -(e.get("last_use") or 0)),
        )
        by_category[cat] = [_compact_word(e) for e in ordered[:per_category]]
        for e in entries:
            if e.get("star"):
                debt_words.append(_compact_word(e, cat))
    return {
        "summary": palette_json.get("summary") or {},
        "debt_words": debt_words,
        "by_category": by_category,
    }


def _compact_grammar_intro(debt: dict) -> dict:
    """Compact grammar-intro recommendations.

    The recommendations are sorted by leverage score (see
    grammar_progression.rank_uncovered). The first item is the
    skill's default pick; the second/third are alternatives the agent
    may swap in if the default doesn't fit the story's premise. Each
    item ships with a `priority_rationale.explanation` string so the
    agent can sanity-check the ranking without reading the scoring code.
    """
    recs = debt.get("recommended_for_this_story") or []
    return {
        "must_introduce": bool(debt.get("must_introduce")),
        "current_jlpt": debt.get("current_jlpt"),
        "coverage_summary": debt.get("coverage_summary"),
        "default_pick_policy": (
            "Pick recommended[0] unless the story's premise makes a "
            "different choice clearly more natural. Document any deferral "
            "in the spec's `intent` field. Recommendations are ranked by "
            "leverage (direct unlocks + paradigm bonus + earlier-tier "
            "bonus) — see grammar_progression.PARADIGM_ANCHORS."
        ),
        "recommended": [
            {
                "catalog_id": r.get("catalog_id"),
                "title": r.get("title"),
                "short": r.get("short"),
                "examples": (r.get("examples") or [])[:2],
                "priority_score":     r.get("priority_score"),
                "priority_rationale": (r.get("priority_rationale") or {}).get("explanation"),
            }
            for r in recs[:5]
        ],
    }


def _compact_vocab_reinforcement(debt: dict) -> dict:
    """Compact view: must-reinforce items first, then a sample of shoulds.

    The author should use every must-reinforce item in this story
    (Rule R1 hard-block); should-reinforce items are gentler reminders.
    """
    items = debt.get("items") or []
    must = [i for i in items if i.get("must_reinforce")]
    should = [i for i in items if i.get("should_reinforce")]
    return {
        "window":               debt.get("window"),
        "min_uses":             debt.get("min_uses"),
        "must_reinforce_count": debt.get("must_reinforce_count", 0),
        "items": [
            {
                "word_id":             i["word_id"],
                "lemma":               i["lemma"],
                "intro_in_story":      i["intro_in_story"],
                "stories_since_intro": i["stories_since_intro"],
                "must_reinforce":      bool(i.get("must_reinforce")),
            }
            for i in (must + should)[:8]
        ],
    }


def _compact_grammar_reinforcement(debt: dict) -> dict:
    items = debt.get("items") or []
    load_bearing = [i for i in items if i.get("must_reinforce")]
    load_bearing.extend(i for i in items if i.get("should_reinforce"))
    return {
        "must_reinforce_count": debt.get("must_reinforce_count", 0),
        "items": [
            {
                "grammar_id": i.get("grammar_id"),
                "must_reinforce": bool(i.get("must_reinforce")),
                "intro_in_story": i.get("intro_in_story"),
                "window_end": i.get("window_end"),
                "example_surface": (i.get("example") or {}).get("surface"),
            }
            for i in load_bearing[:6]
        ],
    }


def _lexical_difficulty_constraints(target_story: int) -> dict:
    """Brief section: spell out the lexical-difficulty cap for this story.

    Tells the author what JLPT level / nf-band the story may mint, and
    lists existing palette words that would EXCEED that cap (so the
    author can avoid drawing them into the next story without
    consciously taking an `lexical_overrides` slot). The override
    discipline mirrors v2 grammar-override discipline: max one per
    story; must be mentioned in the spec's `intent` field.
    """
    try:
        from lexical_difficulty import (  # noqa: E402
            tier_cap,
            difficulty_from_vocab_record,
            evaluate_cap,
            MAX_OVERRIDES_PER_STORY,
        )
    except Exception:
        return {
            "available": False,
            "note": "lexical_difficulty module unavailable",
        }
    cap_jlpt, cap_nf = tier_cap(target_story)
    out: dict[str, Any] = {
        "available": True,
        "cap": {
            "max_jlpt_level": cap_jlpt,
            "max_jlpt_label": f"N{cap_jlpt}",
            "max_nf_band": cap_nf,
            "rule": (
                f"Each newly minted word for story {target_story} must "
                f"satisfy EITHER (a) JLPT level ≤ N{cap_jlpt}, OR "
                f"(b) JMdict nf-band ≤ nf{cap_nf:02d} (i.e. roughly "
                f"top {cap_nf*500:,} in the news-frequency corpus). "
                f"Words with NO frequency signal at all (no JLPT entry, "
                f"no nf-band tag, no `ichi1` basic-vocab tag) are "
                f"automatically above-cap — likely very rare."
            ),
            "max_overrides_per_story": MAX_OVERRIDES_PER_STORY,
            "override_field": "lexical_overrides",
            "override_note": (
                "If a single above-cap word is genuinely load-bearing "
                "for the scene, list it in spec.lexical_overrides "
                "(an array of surface strings) AND mention it in "
                "spec.intent so the choice is visible. The gauntlet "
                "warns on override use; ≥2 overrides hard-fails."
            ),
        },
    }
    # Survey the existing vocab and surface words that are ABOVE this
    # story's cap. These are not banned (they're already in the corpus
    # and the author may want to reuse them — that's even pedagogically
    # good for reinforcement) — but for the AUTHOR to know which ones
    # cost an "override slot" if newly introduced concepts are bolted
    # onto them. In practice this is mostly an informational warning;
    # the cap only fires on NEW mints.
    try:
        from _paths import load_vocab_attributed  # noqa: E402

        vocab = load_vocab_attributed()
    except Exception:
        return out
    above_cap_existing = []
    for wid, w in sorted(vocab.get("words", {}).items()):
        diff = difficulty_from_vocab_record(w)
        dec = evaluate_cap(diff, target_story)
        if dec.above_cap:
            above_cap_existing.append({
                "word_id": wid,
                "surface": w.get("surface", ""),
                "kana": w.get("kana", ""),
                "jlpt": diff.jlpt,
                "nf_band": diff.nf_band,
                "first_story": w.get("first_story"),
                "reason": dec.reason,
            })
    out["existing_above_cap"] = above_cap_existing[:20]  # cap output volume
    out["existing_above_cap_total"] = len(above_cap_existing)
    out["how_to_use"] = (
        "Reusing an above-cap existing word is FINE (it's already in "
        "the corpus and learners have seen it). The cap only blocks "
        "MINTING a new above-cap word. If you must mint one, list it "
        "in spec.lexical_overrides."
    )
    return out


def _literary_contract() -> dict:
    """The compact brief's main purpose: prevent valid-but-dead stories."""
    return {
        "one_sentence_test": (
            "Before drafting, answer: what changes? Use an action/transfer/"
            "discovery verb, not 'the narrator observes X'."
        ),
        "required_arc": [
            "sentence 1 and closer differ in object location/owner/state or narrator knowledge",
            "anchor object appears ≥3 times and causes an action, transfer, or discovery",
            "every character enters the scene and forces action/dialogue/transfer",
            "reflection adds new information; it must not restate the setting",
            "closer has a real verb and does not mirror previous closers",
        ],
        "avoid": [
            "decorative noun that appears once and never pays off",
            "noun-pile closer with です and no verb",
            "AのY は BのY equivalence",
            "静か on inanimate objects",
            "思います for facts already known on the page",
        ],
    }


# ── Public entry point ──────────────────────────────────────────────────────

def build_brief(target_story: int) -> dict[str, Any]:
    palette_json = _palette.build_palette(target_story)
    grammar_palette = _palette.build_grammar_palette(target_story)
    seed_plan = _seed_plan_for_story(target_story)
    # Pull the planned scene_class from the ladder; fall back to the
    # seed plan's `scene_class` field if present (the seed plan can
    # override the ladder for a specific slot, e.g. when the user
    # consciously swaps two slots).
    try:
        from grammar_progression import ladder_for  # noqa: E402
        ladder = ladder_for(target_story)
    except Exception:
        ladder = {"scene_class": None, "in_bootstrap": False,
                  "vocab_min": None, "vocab_max": None,
                  "grammar_min": None, "grammar_max": None}
    planned_scene = seed_plan.get("scene_class") or ladder.get("scene_class")
    return {
        "story_id": target_story,
        "size_band": _size_band_for(target_story),
        "mint_budget": _mint_budget_for(target_story),
        "ladder": ladder,
        "seed_plan": seed_plan,
        "scene_affordances": _scene_affordances_for(planned_scene),
        "palette": palette_json,
        "grammar_points": grammar_palette,
        "grammar_introduction_debt": _grammar_introduction_debt(target_story),
        "grammar_reinforcement_debt": _grammar_reinforcement_debt(target_story),
        "north_stars": _north_stars_stub(target_story),
        "scene_coverage": _scene_coverage_stub(target_story),
        "echo_warnings": _echo_warnings_stub(target_story),
        "reinforcement_debt": _reinforcement_debt_from_palette(palette_json),
        "vocab_reinforcement_debt": _vocab_reinforcement_debt(target_story),
        "r1_strict_required": _r1_strict_required(target_story),
        "lexical_difficulty_constraints": _lexical_difficulty_constraints(target_story),
        "lint_rules_active": _LINT_RULES_ACTIVE,
        "anti_patterns_to_avoid": _ANTI_PATTERNS,
        "previous_3_stories": _previous_3_stories_summary(target_story),
        "previous_closers": _previous_closers(target_story),
        "schema_version": "2026-04-29-v2.5",
    }


def build_author_brief(target_story: int) -> dict[str, Any]:
    """Concise, author-facing brief: load-bearing constraints + story craft.

    `build_brief()` remains the complete data model for validators and tooling.
    This compact view is what an LLM author should read before drafting.
    """
    full = build_brief(target_story)
    ladder = full.get("ladder", {})
    seed_plan = full.get("seed_plan", {})
    return {
        "story_id": target_story,
        "schema_version": "2026-04-29-v2.5-author-compact",
        "hard_limits": {
            "size_band": full["size_band"],
            "mint_budget": {
                k: full["mint_budget"][k]
                for k in ("min", "max", "target", "rationale", "in_bootstrap")
            },
            "ladder": ladder,
            "grammar_max_new": ladder.get("grammar_max"),
            "grammar_min_new": ladder.get("grammar_min"),
            "lexical_difficulty_cap": full.get(
                "lexical_difficulty_constraints", {}
            ).get("cap"),
            "required_spec_fields": [
                "intent", "scene_class", "anchor_object", "characters",
                "sentences[].role",
            ],
        },
        "must_hit": {
            "seed_plan": seed_plan,                 # v2.5 — prescriptive bootstrap seed
            "scene_affordances": full.get("scene_affordances", {}),
            "grammar_reinforcement": _compact_grammar_reinforcement(
                full["grammar_reinforcement_debt"]
            ),
            "grammar_introduction": _compact_grammar_intro(
                full["grammar_introduction_debt"]
            ),
            "word_reinforcement": _compact_vocab_reinforcement(
                full["vocab_reinforcement_debt"]
            ),
            # R1-strict: words this story is FORCED to carry or
            # `test_vocab_words_are_reinforced` will go red after ship.
            # Mirrors the test logic exactly; gauntlet's `step_r1_strict`
            # hard-blocks any wid in `items` not present in built tokens.
            "r1_strict_required": full["r1_strict_required"],
            # Long-tail palette-star debt (words unused for ≥8 stories) is
            # informational, not load-bearing for the next ship.
            "word_palette_debt": full["reinforcement_debt"],
        },
        "storytelling": _literary_contract(),
        "voice_and_variety": {
            "north_stars": full["north_stars"],
            "previous_3_stories": full["previous_3_stories"],
            "previous_closers": full["previous_closers"],
        },
        "palette": _compact_palette(full["palette"]),
        "workflow_reminders": [
            "Pick intent + scene_class + anchor before writing JP.",
            "Use would-mint per candidate sentence; keep mints coherent.",
            "If a grammar obligation harms the story, redesign the scene instead of bolting it on.",
            "Run author_loop.py author N --dry-run before shipping.",
        ],
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
    p.add_argument("--full", action="store_true",
                   help="emit the complete tooling brief instead of the compact author brief")
    p.add_argument("--section",
                   help="emit a single top-level section instead of the selected brief")
    args = p.parse_args()

    target = _parse_target(args.target)
    brief = build_brief(target) if args.full else build_author_brief(target)
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
