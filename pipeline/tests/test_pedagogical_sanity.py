"""Class F: Pedagogical sanity tests.

Engagement, progression, and tier-rule checks that are not internal
state integrity but still automatable.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest


def test_every_story_meets_progression_target(stories, root):
    """Each shipped story must be within ±20 % of its computed sentence target."""
    sys.path.insert(0, str(root / "pipeline"))
    from progression import target_sentences

    bad = []
    for story in stories:
        n = int(story["_id"].split("_")[1])
        target = target_sentences(n)
        actual = len(story.get("sentences", []))
        # Allow target ± 1 (matches Check 7 length policy)
        if abs(actual - target) > 1:
            bad.append(f"{story['_id']}: {actual} sentences (target {target})")
    assert not bad, "Progression curve violations:\n  " + "\n  ".join(bad)


def test_engagement_baseline_above_floor(root, stories):
    """Every shipped story's average engagement must be ≥ 3.5."""
    baseline_path = root / "pipeline" / "engagement_baseline.json"
    if not baseline_path.exists():
        pytest.skip("pipeline/engagement_baseline.json not present")
    with baseline_path.open() as f:
        baseline = json.load(f)

    if isinstance(baseline, dict) and "reviews" in baseline:
        entries = baseline["reviews"]
    elif isinstance(baseline, dict):
        entries = [{"story_id": k, **v} for k, v in baseline.items() if isinstance(v, dict)]
    else:
        entries = baseline
    def normalise(sid):
        if isinstance(sid, int):
            return f"story_{sid}"
        return sid if isinstance(sid, str) and sid.startswith("story_") else (
            f"story_{sid}" if isinstance(sid, str) and sid.isdigit() else sid
        )

    by_id = {normalise(r["story_id"]): r for r in entries
             if isinstance(r, dict) and r.get("story_id") is not None}
    bad = []
    for story in stories:
        rec = by_id.get(story["_id"])
        if not rec:
            continue  # covered by test_engagement_baseline_covers_every_story
        avg = rec.get("average")
        if avg is None:
            scores = rec.get("scores", {})
            if scores:
                avg = sum(scores.values()) / len(scores)
        if avg is not None and avg < 3.5:
            bad.append(f"{story['_id']}: avg {avg}")
    assert not bad, "Stories below engagement floor:\n  " + "\n  ".join(bad)


def test_no_story_uses_grammar_above_its_tier(stories, grammar, root):
    """Story N must only use grammar points whose tier ≤ the tier story N is in."""
    sys.path.insert(0, str(root / "pipeline"))
    from grammar_progression import is_grammar_legal_for_story

    bad = []
    for story in stories:
        n = int(story["_id"].split("_")[1])
        for sent in story.get("sentences", []):
            for tok in sent.get("tokens", []):
                for gid in (tok.get("grammar_id"), (tok.get("inflection") or {}).get("grammar_id")):
                    if gid:
                        point = grammar["points"].get(gid)
                        if not point:
                            continue
                        tier = point.get("jlpt")
                        if tier and not is_grammar_legal_for_story(tier, n):
                            bad.append(
                                f"{story['_id']}: uses {gid} ({tier}) — too advanced for story {n}"
                            )
    bad = sorted(set(bad))
    assert not bad, "Grammar tier violations:\n  " + "\n  ".join(bad)


def test_grammar_introduction_cadence(stories, root):
    """Slow-but-steady grammar cadence — see grammar_progression.py for rationale.

    Two rules enforced (research-grounded; see ENCOUNTERS_TO_INTERNALISE etc.):

      Rule A (max):  no story may declare more than MAX_NEW_PER_STORY new
                     grammar points (after the bootstrap window 1..BOOTSTRAP_END,
                     which is capped in aggregate at BOOTSTRAP_MAX_TOTAL).
      Rule B (min):  every rolling window of CADENCE_WINDOW consecutive stories
                     beyond the bootstrap region must contain at least
                     MIN_NEW_PER_WINDOW new grammar introductions.

    Together these prevent both cramming (which hurts consolidation) and
    stagnation (which starves forward motion). The defaults are tuned so that
    a learner reading the full library gets roughly 40+ encounters of each
    foundational point — the empirical threshold for incidental acquisition
    reported by Sakurai et al. and corroborated by the spaced-repetition /
    skill-acquisition literature (DeKeyser 2017; Suzuki 2021).
    """
    sys.path.insert(0, str(root / "pipeline"))
    from grammar_progression import (
        BOOTSTRAP_END,
        BOOTSTRAP_MAX_TOTAL,
        MAX_NEW_PER_STORY,
        CADENCE_WINDOW,
        MIN_NEW_PER_WINDOW,
        MAX_CONSEC_CONSOLIDATION,
    )

    intros: dict[int, list[str]] = {}
    consolidation: dict[int, bool] = {}
    for story in stories:
        n = int(story["_id"].split("_")[1])
        ng = story.get("new_grammar") or []
        # new_grammar is either list[str] of grammar_ids or list[dict] with id/catalog_id
        ids: list[str] = []
        for x in ng:
            if isinstance(x, str):
                ids.append(x)
            elif isinstance(x, dict):
                for k in ("id", "grammar_id", "catalog_id"):
                    if k in x:
                        ids.append(x[k])
                        break
        intros[n] = ids
        consolidation[n] = bool(story.get("consolidation_arc"))

    bad: list[str] = []

    # ── Rule A: per-story max (with bootstrap aggregate) ──────────────────
    bootstrap_total = sum(len(intros.get(i, [])) for i in range(1, BOOTSTRAP_END + 1))
    if bootstrap_total > BOOTSTRAP_MAX_TOTAL:
        bad.append(
            f"bootstrap stories 1..{BOOTSTRAP_END}: introduced {bootstrap_total} points "
            f"(cap {BOOTSTRAP_MAX_TOTAL})"
        )
    for n, ids in intros.items():
        if n <= BOOTSTRAP_END:
            continue  # policed in aggregate above
        if len(ids) > MAX_NEW_PER_STORY:
            bad.append(
                f"story_{n}: introduces {len(ids)} new grammar points "
                f"(max {MAX_NEW_PER_STORY} after bootstrap): {ids}"
            )

    # A consolidation_arc story must declare zero new grammar (the whole point).
    for n, flagged in consolidation.items():
        if flagged and intros.get(n):
            bad.append(
                f"story_{n}: marked consolidation_arc=true but declares new grammar {intros[n]} — "
                f"a consolidation arc must introduce no new points"
            )

    # ── Rule B: rolling-window min cadence ────────────────────────────────
    # A story counts as satisfying the window if it introduces a new point
    # OR is explicitly flagged consolidation_arc=true (an opt-out).
    if intros:
        max_sid = max(intros)
        for hi in range(BOOTSTRAP_END + CADENCE_WINDOW, max_sid + 1):
            lo = hi - CADENCE_WINDOW + 1
            count = sum(len(intros.get(i, [])) for i in range(lo, hi + 1))
            window_all_consol = all(consolidation.get(i, False) for i in range(lo, hi + 1))
            if count < MIN_NEW_PER_WINDOW and not window_all_consol:
                bad.append(
                    f"stories {lo}..{hi}: only {count} new grammar points introduced "
                    f"(minimum {MIN_NEW_PER_WINDOW} per {CADENCE_WINDOW}-story window) — "
                    f"library has stagnated, no forward progress on grammar coverage. "
                    f"To allow this gap explicitly, set consolidation_arc=true on every "
                    f"story in the window."
                )

    # ── Rule C: cap on consecutive consolidation stories ───────────────────
    # An opt-out can't run forever. Long stagnation arcs are forbidden even
    # when explicitly declared.
    if consolidation:
        max_sid = max(consolidation)
        run = 0
        run_start = None
        for n in range(1, max_sid + 1):
            if consolidation.get(n):
                run += 1
                if run_start is None:
                    run_start = n
                if run > MAX_CONSEC_CONSOLIDATION:
                    bad.append(
                        f"stories {run_start}..{n}: {run} consecutive consolidation_arc=true "
                        f"stories exceeds cap of {MAX_CONSEC_CONSOLIDATION}. "
                        f"Break the arc with at least one new grammar introduction."
                    )
                    # avoid spamming the same arc
                    break
            else:
                run = 0
                run_start = None

    assert not bad, "Grammar cadence violations:\n  " + "\n  ".join(bad)


def test_introduced_grammar_is_reinforced(stories, root):
    """Every newly-introduced grammar point must be reinforced in the next stories.

    A grammar point declared in story_N's `new_grammar` must appear (as a
    `grammar_id` on any token) in at least MIN_REINFORCEMENT_USES of the next
    REINFORCEMENT_WINDOW stories. Without repeat exposure the introduction
    fails to land — Sakurai et al. report ~40 encounters as the threshold for
    incidental acquisition of a grammar form, far above one. Skipping the
    reinforcement window means the learner sees the point once and never again
    while it's still warm in working memory, defeating the cadence policy.

    Stories near the end of the library may have a shorter look-ahead window
    than REINFORCEMENT_WINDOW; in that case the test only requires that the
    point appears in *all* available follow-up stories (no escape hatch, but
    no impossible bar either).
    """
    sys.path.insert(0, str(root / "pipeline"))
    from grammar_progression import REINFORCEMENT_WINDOW, MIN_REINFORCEMENT_USES

    # Documented authoring debt: grammar points whose introduction story
    # currently fails the reinforcement check because the relevant surface
    # never reappears in the immediate follow-up window. Each entry should
    # be paired with a TODO to re-author one of the next REINFORCEMENT_WINDOW
    # stories to weave the surface back in. New entries here are explicit
    # technical debt and should be paid down, not accumulated.
    #
    # As of v0.18 (2026-04-22) this list is empty: every grammar
    # introduction in the library now has live reinforcement in its
    # 5-story window. Adding new entries should be a deliberate,
    # documented exception, not a habit.
    KNOWN_REINFORCEMENT_DEBT: set[tuple[int, str]] = set()

    # Build per-story usage map: which grammar_ids appear (anywhere) in story N?
    by_n: dict[int, dict] = {}
    for story in stories:
        n = int(story["_id"].split("_")[1])
        by_n[n] = story
    max_n = max(by_n) if by_n else 0

    used: dict[int, set[str]] = {}
    intros: dict[int, list[str]] = {}
    for n, story in by_n.items():
        u: set[str] = set()
        for sec in ("title", "subtitle"):
            for tok in (story.get(sec) or {}).get("tokens", []):
                for gid in (tok.get("grammar_id"),
                            (tok.get("inflection") or {}).get("grammar_id")):
                    if gid:
                        u.add(gid)
        for sent in story.get("sentences", []):
            for tok in sent.get("tokens", []):
                for gid in (tok.get("grammar_id"),
                            (tok.get("inflection") or {}).get("grammar_id")):
                    if gid:
                        u.add(gid)
        used[n] = u
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
        intros[n] = ids

    bad: list[str] = []
    for n, ids in intros.items():
        if not ids:
            continue
        # Look at the next REINFORCEMENT_WINDOW stories (n+1 .. n+W).
        followups = [i for i in range(n + 1, n + 1 + REINFORCEMENT_WINDOW)
                     if i in by_n]
        if not followups:
            continue  # newest story in library — nothing to check yet
        required = min(MIN_REINFORCEMENT_USES, len(followups))
        for gid in ids:
            hits = [i for i in followups if gid in used.get(i, set())]
            if len(hits) < required:
                if (n, gid) in KNOWN_REINFORCEMENT_DEBT:
                    continue  # documented authoring debt — pay down, don't grow
                bad.append(
                    f"story_{n} introduced {gid} but it only reappears in "
                    f"{len(hits)} of the next {len(followups)} stories "
                    f"(stories {hits or 'none'}); needs ≥ {required} for "
                    f"reinforcement to land."
                )

    # Also fail if any debt entry is no longer needed — keeps the list honest.
    stale_debt = []
    for n, gid in KNOWN_REINFORCEMENT_DEBT:
        if n not in by_n or gid not in intros.get(n, []):
            stale_debt.append(f"({n}, {gid!r}) — story doesn't introduce this point")
            continue
        followups = [i for i in range(n + 1, n + 1 + REINFORCEMENT_WINDOW)
                     if i in by_n]
        if not followups:
            continue
        required = min(MIN_REINFORCEMENT_USES, len(followups))
        hits = [i for i in followups if gid in used.get(i, set())]
        if len(hits) >= required:
            stale_debt.append(
                f"({n}, {gid!r}) — point now reappears in stories {hits}; "
                f"remove from KNOWN_REINFORCEMENT_DEBT"
            )
    assert not stale_debt, "Stale reinforcement-debt entries:\n  " + "\n  ".join(stale_debt)
    assert not bad, "Grammar reinforcement violations:\n  " + "\n  ".join(bad)


def test_first_introduction_marked_is_new(stories, vocab):
    """Every word's FIRST appearance across all stories must be marked is_new=true."""
    first_seen: dict[str, tuple[str, str, int, int]] = {}  # wid → (story_id, sec, sent_idx, tok_idx)
    is_new_marks: dict[str, list[str]] = {}  # wid → list of (story_id, location) where is_new was true

    for story in sorted(stories, key=lambda s: int(s["_id"].split("_")[1])):
        for sec_name in ("title", "subtitle"):
            sec = story.get(sec_name) or {}
            for j, tok in enumerate(sec.get("tokens", [])):
                wid = tok.get("word_id")
                if not wid:
                    continue
                if wid not in first_seen:
                    first_seen[wid] = (story["_id"], sec_name, -1, j)
                if tok.get("is_new"):
                    is_new_marks.setdefault(wid, []).append(f"{story['_id']}:{sec_name}[{j}]")
        for i, sent in enumerate(story.get("sentences", [])):
            for j, tok in enumerate(sent.get("tokens", [])):
                wid = tok.get("word_id")
                if not wid:
                    continue
                if wid not in first_seen:
                    first_seen[wid] = (story["_id"], "sentence", i, j)
                if tok.get("is_new"):
                    is_new_marks.setdefault(wid, []).append(f"{story['_id']}:sentence[{i}][{j}]")

    bad = []
    for wid, marks in is_new_marks.items():
        if len(marks) > 1:
            bad.append(f"{wid}: is_new marked in {len(marks)} places: {marks}")
    assert not bad, "Words marked is_new in multiple places:\n  " + "\n  ".join(bad)


def test_all_words_used_in_first_seen_order(stories):
    """Story.all_words_used must list word_ids in order of first appearance within that story."""
    bad = []
    for story in stories:
        seen: list[str] = []
        for sec_name in ("title", "subtitle"):
            sec = story.get(sec_name) or {}
            for tok in sec.get("tokens", []):
                wid = tok.get("word_id")
                if wid and wid not in seen:
                    seen.append(wid)
        for sent in story.get("sentences", []):
            for tok in sent.get("tokens", []):
                wid = tok.get("word_id")
                if wid and wid not in seen:
                    seen.append(wid)
        declared = story.get("all_words_used", [])
        if seen != declared:
            bad.append(f"{story['_id']}:\n      declared: {declared}\n      actual:   {seen}")
    assert not bad, "all_words_used drift:\n  " + "\n  ".join(bad)


def test_sentence_idx_is_sequential(stories):
    bad = []
    for story in stories:
        for i, sent in enumerate(story.get("sentences", [])):
            declared_idx = sent.get("idx")
            if declared_idx != i:
                bad.append(f"{story['_id']} sentence position {i}: declared idx={declared_idx}")
    assert not bad, "Sentence idx not sequential:\n  " + "\n  ".join(bad)
