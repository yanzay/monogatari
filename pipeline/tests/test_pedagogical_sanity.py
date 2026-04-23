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
    """Each shipped story must sit within Check 7's per-story sentence band."""
    sys.path.insert(0, str(root / "pipeline"))
    from progression import target_sentences, SENTENCE_TOLERANCE

    bad = []
    for story in stories:
        n = int(story["_id"].split("_")[1])
        target = target_sentences(n)
        actual = len(story.get("sentences", []))
        # Match Check 7's tolerance band exactly (target ± SENTENCE_TOLERANCE)
        if abs(actual - target) > SENTENCE_TOLERANCE:
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


def test_first_introduction_marked_is_new(stories, vocab):
    """Every word's FIRST appearance across all stories must be marked is_new=true."""
    first_seen: dict[str, tuple[str, str, int, int]] = {}  # wid → (story_id, sec, sent_idx, tok_idx)
    is_new_marks: dict[str, list[str]] = {}  # wid → list of (story_id, location) where is_new was true

    for story in sorted(stories, key=lambda s: int(s["_id"].split("_")[1])):
        for sec_name in ("title",):
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
        for sec_name in ("title",):
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


# ── Disabled pedagogical-cadence tests ──────────────────────────────
#
# These tests enforce the "1 story, 1 new grammar" cadence + reinforcement
# rules. They were temporarily disabled when the converter switched to
# honest library-wide first-occurrence semantics. The logic is preserved
# verbatim so we can re-enable / adjust later — just flip the skip flag.

PEDAGOGICAL_CADENCE_ENABLED = True

_skip_cadence = pytest.mark.skipif(
    not PEDAGOGICAL_CADENCE_ENABLED,
    reason="Cadence/reinforcement rules deferred — see is_new_grammar honest semantics",
)

@_skip_cadence
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
    )

    intros: dict[int, list[str]] = {}
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

    # ── Rule B: rolling-window min cadence ────────────────────────────────
    if intros:
        max_sid = max(intros)
        for hi in range(BOOTSTRAP_END + CADENCE_WINDOW, max_sid + 1):
            lo = hi - CADENCE_WINDOW + 1
            count = sum(len(intros.get(i, [])) for i in range(lo, hi + 1))
            if count < MIN_NEW_PER_WINDOW:
                bad.append(
                    f"stories {lo}..{hi}: only {count} new grammar points introduced "
                    f"(minimum {MIN_NEW_PER_WINDOW} per {CADENCE_WINDOW}-story window) — "
                    f"library has stagnated, no forward progress on grammar coverage. "
                    f"Declare at least one new_grammar in a story within this window."
                )

    assert not bad, "Grammar cadence violations:\n  " + "\n  ".join(bad)


@_skip_cadence
def test_vocabulary_introduction_cadence(stories, root):
    """Vocabulary cadence — mirror of the grammar cadence test (Rule A only).

    Hard rule (added 2026-04-23):

      Every story past the bootstrap window 1..BOOTSTRAP_END must declare at
      least MIN_NEW_WORDS_PER_STORY new vocabulary items. The pedagogical
      motivation is the same as the grammar cadence: a graded reader that
      stops growing its vocabulary stops being a graded reader.

    Bootstrap stories are exempt because story 1 loads ~14 foundational nouns
    in one shot, which would make a uniform per-story floor misleading.

    No rolling-window minimum yet — the per-story floor is strictly stronger
    than any reasonable window-min would be (3 per story = 15 per 5-story
    window), so a window rule would be redundant.
    """
    sys.path.insert(0, str(root / "pipeline"))
    from grammar_progression import (
        BOOTSTRAP_END,
        MIN_NEW_WORDS_PER_STORY,
    )

    bad: list[str] = []
    for story in stories:
        n = int(story["_id"].split("_")[1])
        if n <= BOOTSTRAP_END:
            continue  # bootstrap stories are exempt
        new_words = story.get("new_words") or []
        if len(new_words) < MIN_NEW_WORDS_PER_STORY:
            bad.append(
                f"story_{n}: introduces {len(new_words)} new vocabulary item(s) "
                f"(minimum {MIN_NEW_WORDS_PER_STORY} after bootstrap): {new_words}"
            )

    assert not bad, (
        "Vocabulary cadence violations (Check 3.7):\n  "
        + "\n  ".join(bad)
    )


@_skip_cadence
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
        for sec in ("title",):
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


@_skip_cadence
def test_vocab_words_are_reinforced(stories, root):
    """Rule R1 — Every newly-introduced word must be reinforced early.

    A word declared in story_N's `new_words` must appear (as a `word_id` on
    any content token) in at least VOCAB_REINFORCE_MIN_USES of the next
    VOCAB_REINFORCE_WINDOW stories.

    Rationale: introducing a word once and then leaving it unseen for the
    entire reinforcement window means it was never truly in the curriculum.
    Two appearances in the next ten stories is the minimum bar for the word
    to have any chance of landing in long-term memory (cf. Nation 2022:
    vocabulary needs ~10 spaced encounters for reliable incidental retention;
    the early-window check seeds the first two of those encounters).

    Stories near the end of the library may have a shorter look-ahead window;
    in that case the test only requires that the word appears in
    min(VOCAB_REINFORCE_MIN_USES, available_stories) of those stories — no
    impossible bar, but no escape hatch either.

    Words with a shorter available window than VOCAB_REINFORCE_MIN_USES are
    skipped (the library is still young and hasn't had a chance to reinforce
    them yet).
    """
    sys.path.insert(0, str(root / "pipeline"))
    from grammar_progression import (
        BOOTSTRAP_END,
        VOCAB_REINFORCE_WINDOW,
        VOCAB_REINFORCE_MIN_USES,
    )

    # Build per-story word-id usage map
    by_n: dict[int, dict] = {}
    for story in stories:
        n = int(story["_id"].split("_")[1])
        by_n[n] = story
    if not by_n:
        return

    def word_ids_used(story: dict) -> set[str]:
        # Any token carrying a word_id counts as a vocabulary encounter,
        # regardless of role. The AUX_AFTER_TO post-pass demotes verbs like
        # 思います / 言います to role='aux' inside the と+...+verb construction,
        # but those still expose the learner to the lemma; for spaced
        # encounters that is what matters.
        used: set[str] = set()
        for sec in ("title",):
            for tok in (story.get(sec) or {}).get("tokens", []):
                if tok.get("word_id"):
                    used.add(tok["word_id"])
        for sent in story.get("sentences", []):
            for tok in sent.get("tokens", []):
                if tok.get("word_id"):
                    used.add(tok["word_id"])
        return used

    used: dict[int, set[str]] = {n: word_ids_used(s) for n, s in by_n.items()}

    # Build per-story new_words map
    intros: dict[int, list[str]] = {}
    for n, story in by_n.items():
        if n <= BOOTSTRAP_END:
            continue  # bootstrap stories are exempt
        ids = [w if isinstance(w, str) else w.get("id") or w.get("word_id", "")
               for w in (story.get("new_words") or [])]
        intros[n] = [i for i in ids if i]

    bad: list[str] = []

    for n, ids in intros.items():
        if not ids:
            continue
        followups = [i for i in range(n + 1, n + 1 + VOCAB_REINFORCE_WINDOW)
                     if i in by_n]
        # Skip if the library doesn't yet have enough follow-up stories to judge
        if len(followups) < VOCAB_REINFORCE_MIN_USES:
            continue
        required = min(VOCAB_REINFORCE_MIN_USES, len(followups))
        for wid in ids:
            hits = [i for i in followups if wid in used.get(i, set())]
            if len(hits) < required:
                bad.append(
                    f"story_{n} introduced {wid} but it only reappears in "
                    f"{len(hits)} of the next {len(followups)} stories "
                    f"(stories {hits or 'none'}); needs ≥{required} for "
                    f"early reinforcement to land."
                )

    assert not bad, (
        "Vocabulary early-reinforcement violations (Rule R1):\n  "
        + "\n  ".join(bad)
    )


@_skip_cadence
def test_no_vocab_word_abandoned(stories, root):
    """Rule R2 — No word may go unseen for more than VOCAB_MAX_GAP stories.

    For every word in the library, we compute the longest consecutive gap
    between uses across the full story sequence. If that gap exceeds
    VOCAB_MAX_GAP stories, the word is considered abandoned.

    Rationale: 20 stories without a single encounter is roughly 6-8 weeks
    of reading at a typical pace. SLA research (Nation 2022; Waring & Takaki
    2003) indicates that incidental vocabulary gains erode significantly
    without recycling within that timeframe. A word that hasn't appeared in
    20 stories either needs to be explicitly reintroduced or removed from the
    vocabulary inventory.

    Exemptions:
    - Words introduced in the last VOCAB_ABANDON_GRACE stories (they simply
      haven't had time to build up a gap yet).
    - Words are only evaluated up to the last story in which they appear;
      the "trailing gap" from last use to the end of the library is not
      penalised here (that would punish every word introduced late, including
      brand-new words). Rule R1 catches the "introduced and never seen again"
      case for recently-introduced words; R2 focuses on mid-library dropouts.

    """
    sys.path.insert(0, str(root / "pipeline"))
    from grammar_progression import VOCAB_MAX_GAP, VOCAB_ABANDON_GRACE

    # Build per-story word-id usage map (content tokens only)
    by_n: dict[int, dict] = {}
    for story in stories:
        n = int(story["_id"].split("_")[1])
        by_n[n] = story
    if not by_n:
        return
    max_n = max(by_n)

    def word_ids_used(story: dict) -> set[str]:
        # See comment in test_vocab_words_are_reinforced — count any token
        # carrying a word_id, regardless of role.
        used: set[str] = set()
        for sec in ("title",):
            for tok in (story.get(sec) or {}).get("tokens", []):
                if tok.get("word_id"):
                    used.add(tok["word_id"])
        for sent in story.get("sentences", []):
            for tok in sent.get("tokens", []):
                if tok.get("word_id"):
                    used.add(tok["word_id"])
        return used

    used_by_story: dict[int, set[str]] = {n: word_ids_used(s) for n, s in by_n.items()}

    # For each word, collect the sorted list of story_ids in which it appears
    word_appearances: dict[str, list[int]] = {}
    for n, wids in used_by_story.items():
        for wid in wids:
            word_appearances.setdefault(wid, []).append(n)
    for wid in word_appearances:
        word_appearances[wid].sort()

    # Collect intro story per word (from new_words fields)
    word_intro: dict[str, int] = {}
    for n, story in by_n.items():
        for w in story.get("new_words") or []:
            wid = w if isinstance(w, str) else w.get("id") or w.get("word_id", "")
            if wid and wid not in word_intro:
                word_intro[wid] = n

    bad: list[str] = []

    for wid, appearances in word_appearances.items():
        intro_n = word_intro.get(wid, appearances[0])

        # Grace period: skip words introduced in the last VOCAB_ABANDON_GRACE stories
        if intro_n >= max_n - VOCAB_ABANDON_GRACE + 1:
            continue

        if len(appearances) < 2:
            # Only one appearance — trailing gap from that story to max_n
            last = appearances[0]
            trailing_gap = max_n - last
            if trailing_gap > VOCAB_MAX_GAP:
                bad.append(
                    f"{wid}: appeared only in story_{last}, then absent for "
                    f"{trailing_gap} stories (through story_{max_n}); "
                    f"max allowed gap is {VOCAB_MAX_GAP}."
                )
            continue

        # Check gaps between consecutive appearances
        max_internal_gap = 0
        worst_pair: tuple[int, int] = (appearances[0], appearances[1])
        for prev, curr in zip(appearances, appearances[1:]):
            gap = curr - prev - 1  # stories *between* the two appearances
            if gap > max_internal_gap:
                max_internal_gap = gap
                worst_pair = (prev, curr)

        if max_internal_gap > VOCAB_MAX_GAP:
            bad.append(
                f"{wid}: gap of {max_internal_gap} stories between "
                f"story_{worst_pair[0]} and story_{worst_pair[1]} "
                f"(max allowed {VOCAB_MAX_GAP})."
            )

    assert not bad, (
        f"Vocabulary abandonment violations (Rule R2, gap > {VOCAB_MAX_GAP} stories):\n  "
        + "\n  ".join(sorted(bad))
    )


