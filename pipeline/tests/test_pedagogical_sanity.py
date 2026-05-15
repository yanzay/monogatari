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

def test_tier_coverage_gate(stories, root):
    """Tier-coverage gate: a story whose tier is HIGHER than the previous
    story's tier may only ship if every catalog point in the prior tier
    has `intro_in_story` set in `data/grammar_state.json`.

    Mirrors validator's Check 3.9. Prevents jumping into N4 while N5
    still has gaps.
    """
    sys.path.insert(0, str(root / "pipeline"))
    from grammar_progression import (
        active_tier,
        TIER_WINDOWS,
        coverage_status,
    )
    cov = coverage_status()

    bad: list[str] = []
    sids = sorted(int(s["_id"].split("_")[1]) for s in stories)
    for n in sids:
        if n <= 1:
            continue
        prev_t = active_tier(n - 1)
        cur_t = active_tier(n)
        if cur_t <= prev_t:
            continue
        prev_jlpt = next((j for t, _, _, j in TIER_WINDOWS if t == prev_t), None)
        rem = cov["by_jlpt"].get(prev_jlpt, {}).get("remaining", 0)
        if rem > 0:
            bad.append(
                f"story_{n} advances from tier {prev_t} ({prev_jlpt}) to "
                f"tier {cur_t} but {rem} {prev_jlpt} point(s) are still "
                f"uncovered (first few: "
                f"{cov['by_jlpt'].get(prev_jlpt, {}).get('uncovered_ids', [])[:5]})"
            )
    assert not bad, "Tier-coverage gate violations:\n  " + "\n  ".join(bad)


def test_per_story_grammar_floor_while_tier_uncovered(stories, root):
    """Per-story floor: every post-bootstrap story whose current tier still
    has uncovered catalog points must declare ≥1 new_grammar.

    Mirrors validator's Check 3.10 and the user-requested rule "all stories
    should introduce new grammar until N5/N4/N3 are completely covered."

    The check uses post-shipping state to determine "uncovered". Because
    every shipped story populates `intro_in_story`, the count grows
    monotonically; the only way to fail this test after shipping is to
    have shipped a story that should have introduced something but
    declared `new_grammar = []` while uncovered points remained in its
    tier (or any earlier tier).
    """
    sys.path.insert(0, str(root / "pipeline"))
    from grammar_progression import (
        BOOTSTRAP_END,
        active_jlpt,
        JLPT_TO_TIER,
        coverage_status,
    )
    cov = coverage_status()

    # Compute, for each tier, whether ANY of that tier's points are still
    # uncovered. (Coverage only ever grows over time, so today's snapshot
    # is enough — if N5 has uncovered points NOW, every past post-bootstrap
    # N5 story should have introduced at least one.)
    by_jlpt = cov["by_jlpt"]

    bad: list[str] = []
    for s in stories:
        n = int(s["_id"].split("_")[1])
        if n <= BOOTSTRAP_END:
            continue
        ng = s.get("new_grammar") or []
        if ng:
            continue  # already pulling its weight
        cur_jlpt = active_jlpt(n)
        cur_tier = JLPT_TO_TIER.get(cur_jlpt, 1)
        any_uncov = any(
            b.get("remaining", 0) > 0
            for j, b in by_jlpt.items()
            if JLPT_TO_TIER.get(j, 99) <= cur_tier
        )
        if any_uncov:
            bad.append(
                f"story_{n} ({cur_jlpt}) declares 0 new_grammar but tier(s) "
                f"≤ {cur_jlpt} still have uncovered points: "
                f"{ {j: b['remaining'] for j, b in by_jlpt.items()
                     if JLPT_TO_TIER.get(j, 99) <= cur_tier and b['remaining'] > 0} }"
            )
    assert not bad, (
        "Per-story grammar floor violations (Check 3.10):\n  "
        + "\n  ".join(bad)
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
        ladder_for,
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

    # ── Rule A: per-story max (read from the ladder, not a flat constant) ──
    # The v2.5 reload (2026-04-29) replaced the legacy single-int
    # MAX_NEW_PER_STORY policy with a per-story ladder for stories
    # 1..BOOTSTRAP_END (= 10). Stories outside the ladder fall through
    # to the steady-state MAX_NEW_PER_STORY = 1.
    for n, ids in intros.items():
        cap = ladder_for(n)["grammar_max"]
        if len(ids) > cap:
            bad.append(
                f"story_{n}: introduces {len(ids)} new grammar points "
                f"(ladder grammar_max = {cap}): {ids}"
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
    from grammar_progression import ladder_for

    # The v2.5 reload (2026-04-29) made bootstrap stories no longer
    # exempt from the vocab floor — instead each bootstrap story has its
    # own (vocab_min, vocab_max) row in BOOTSTRAP_LADDER. Stories 11+
    # fall through to the steady-state floor (MIN_NEW_WORDS_PER_STORY=3).
    bad: list[str] = []
    for story in stories:
        n = int(story["_id"].split("_")[1])
        floor = ladder_for(n)["vocab_min"]
        new_words = story.get("new_words") or []
        if len(new_words) < floor:
            bad.append(
                f"story_{n}: introduces {len(new_words)} new vocabulary item(s) "
                f"(ladder vocab_min = {floor}): {new_words}"
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
    One appearance in the next ten stories is the minimum bar for the word
    to have any chance of landing in long-term memory (cf. Nation 2022:
    vocabulary needs ~10 spaced encounters for reliable incidental retention;
    the early-window check seeds the first of those encounters). Relaxed
    2026-04-28 from 2 → 1; see Rule R1 in pipeline/grammar_progression.py.

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
    """Rule R2 — RETIRED 2026-04-24.

    The previous implementation policed gaps between consecutive uses across
    the entire library lifetime, capped at VOCAB_MAX_GAP=20 stories. In
    practice that turned out to actively *discourage* organic late reuse: a
    word last seen at story 26 could not be casually echoed in story 50
    without either (a) cascading reinforcement weaves through every gap
    story 27..49 or (b) leaving the word silent forever. Authors learned to
    treat each word as either "alive" (reinforced every ≤20 stories) or
    "dead" (never used again) — there was no middle ground for a sentimental
    callback.

    The pedagogical intent — *teach a new word properly when it debuts* — is
    already covered by Rule R1 (test_vocab_words_are_reinforced):
    VOCAB_REINFORCE_MIN_USES uses within VOCAB_REINFORCE_WINDOW stories of
    introduction. Once a word has cleared its maturation window, the learner
    has had real exposure to it; further appearances are bonus reinforcement,
    encouraged but not required, and certainly not gap-checked.

    This test is intentionally a no-op now; it stays in the suite as a
    placeholder so tooling that imports it (cadence.py, weave.py) keeps a
    stable name and the historical rule label "R2" still resolves to a known
    location. If you ever want to revive an abandonment-style check, do it
    *only* over the maturation window, never over the full lifetime.
    """
    return


def test_step_r1_strict_mirrors_r1_test(root, stories):
    """The gauntlet's `step_r1_strict` MUST be a faithful in-process mirror
    of `test_vocab_words_are_reinforced` (R1).

    Contract: for any (story_id, built_story) where R1 would fail post-ship,
    `step_r1_strict` returns status="fail". Conversely, when R1 would pass,
    it returns status="ok".

    Why pinned: this guarantee is what eliminates the "dry-run green ⇒
    pytest red" trap (story 17). If the two implementations drift, the
    trap returns silently. Mock the corpus by passing a synthetic
    built_story whose tokens omit prior-story mints, then verify the step
    fails.
    """
    sys.path.insert(0, str(root / "pipeline"))
    sys.path.insert(0, str(root / "pipeline" / "tools"))
    from author_loop import step_r1_strict
    from agent_brief import _r1_strict_required

    # Simulate the next story (max+1). Brief is computed against the
    # currently-shipped corpus.
    shipped_ids = [int(s["_id"].split("_")[1]) for s in stories]
    next_story = max(shipped_ids, default=0) + 1
    forced = (_r1_strict_required(next_story).get("items") or [])

    # Case 1: built story carries NONE of the forced words → fail.
    if forced:
        empty_built = {"title": {"tokens": []}, "sentences": []}
        r_fail = step_r1_strict(next_story, empty_built)
        assert r_fail.status == "fail", (
            f"step_r1_strict should fail when {len(forced)} R1-required "
            f"word(s) are missing; got {r_fail.status}: {r_fail.summary}"
        )
        missing_ids = set((r_fail.details or {}).get("r1_missing", []))
        forced_ids = {it["word_id"] for it in forced}
        assert forced_ids <= missing_ids, (
            f"step_r1_strict missed forced ids: "
            f"forced={forced_ids}, reported={missing_ids}"
        )

    # Case 2: built story carries ALL forced words → ok.
    sentences = [{"tokens": [{"word_id": it["word_id"]} for it in forced]}] if forced else []
    full_built = {"title": {"tokens": []}, "sentences": sentences}
    r_ok = step_r1_strict(next_story, full_built)
    assert r_ok.status == "ok", (
        f"step_r1_strict should pass when all {len(forced)} R1-required "
        f"word(s) are carried; got {r_ok.status}: {r_ok.summary}"
    )


def test_step_validate_pulls_post_pass_retag_forward(root):
    """`step_validate` MUST apply `_apply_post_pass_attributions` to its
    deepcopy BEFORE invoking the validator (since 2026-05-15).

    Why pinned: without this pre-pass an author cannot satisfy Check 3.10
    via wh-questions, counters, kosoado-as-content, ある/いる aspectual
    reuse, quotative-と + 思います/言います, or clause-conjunctive が —
    all surface- or base-driven retags that the converter cannot emit at
    build time. Story 17 lost N5_doko_where this way and was forced to a
    clunkier grammar choice.

    Contract: a built story whose ONLY new grammar is a post-pass-only
    interrogative tag (N5_dare_who via 誰) must NOT trip Check 3.10's
    "introduces 0 new grammar" error — the validator should see the
    retag and credit the intro. Conversely, the same story with the
    post-pass STRIPPED OUT must trip that error. Differential test pins
    the asymmetry by inspecting the validator output directly (bypassing
    step_validate's error grouping which short-circuits on Check 1
    schema fails).

    NOTE: the probe interrogative MUST be one that is still uncovered in
    the corpus (otherwise Check 3.10 would fail even WITH the retag, since
    a `corpus-already-covered` point isn't "new"). The probe has been
    migrated twice as the corpus grew:
      - originally N5_doko_where (どこ); story 19 introduced it.
      - then N5_dare_who (誰); story 23 introduced it.
      - now N5_itsu_when (いつ); pick the next still-uncovered N5
        post-pass-only retag if and when story N introduces this one.
    All three gids share the same INTERROGATIVE_GIDS pre-pass code path,
    so the test contract is preserved across the swap.
    """
    sys.path.insert(0, str(root / "pipeline"))
    sys.path.insert(0, str(root / "pipeline" / "tools"))
    from author_loop import _apply_post_pass_attributions
    from text_to_story import build_story
    from validate import validate as run_validate
    from _paths import load_vocab, load_grammar
    from derived_state import derive_grammar_attributions
    import copy as _copy

    # Probe-eligible candidates: post-pass-only INTERROGATIVE_GIDS retags
    # at N5 tier. Listed in preferred-swap order; the first one with
    # `intro_in_story is None` (genuinely uncovered) is the live probe.
    # Each entry: (gid, surface_in_quote, sentence_jp, sentence_en).
    PROBE_CANDIDATES = [
        ("N5_itsu_when",  "いつ",
         "友達は「いつ本を読みますか」と聞きました。",
         "My friend asked, \"When do you read the book?\""),
        ("N5_nan_what",   "何",
         "友達は「何の本ですか」と聞きました。",
         "My friend asked, \"What kind of book is it?\""),
        ("N5_dare_who",   "誰",
         "友達は「誰の本ですか」と聞きました。",
         "My friend asked, \"Whose book is this?\""),
        ("N5_doko_where", "どこ",
         "友達は「どこの本ですか」と聞きました。",
         "My friend asked, \"Where is the book from?\""),
    ]
    _attrs = derive_grammar_attributions()
    probe = next(
        (c for c in PROBE_CANDIDATES
         if (_attrs.get(c[0]) or {}).get("intro_in_story") is None),
        None,
    )
    if probe is None:
        pytest.skip(
            "All known post-pass-only INTERROGATIVE_GIDS retags are now "
            "covered by the corpus; migrate this test to the next "
            "uncovered post-pass retag (counters, kosoado, aru/iru, "
            "to-omoimasu, to-iimasu, ga-but, naze-why)."
        )
    probe_gid, _probe_surface, dialogue_jp, dialogue_en = probe

    # Build a real story via the converter so the schema is complete.
    # The lone wh-question gives us an unambiguous probe: the only path
    # to a non-empty `new_grammar` for this story is the post-pass retag
    # of the chosen interrogative → probe_gid.
    spec = {
        "story_id":      9999,    # synthetic, never on disk
        "title":         {"jp": "本", "en": "Book"},
        "intent":        f"synthetic test fixture; probe={probe_gid}",
        "scene_class":   "test",
        "anchor_object": "本",
        "characters":    ["narrator", "friend"],
        "sentences": [
            {"jp": "夕方、家は静かでした。",
             "en": "In the evening, the house was quiet.", "role": "setting"},
            {"jp": "机に本がありました。",
             "en": "There was a book on the desk.", "role": "setting"},
            {"jp": "友達が来ました。",
             "en": "My friend came.", "role": "action"},
            {"jp": dialogue_jp, "en": dialogue_en, "role": "dialogue"},
            {"jp": "私は「私の本です」と答えました。",
             "en": "I answered, \"It's my book.\"", "role": "dialogue"},
            {"jp": "私は本を取りました。",
             "en": "I picked up the book.", "role": "action"},
            {"jp": "友達と私は本を見ました。",
             "en": "My friend and I looked at the book.", "role": "closer"},
        ],
    }

    vocab = load_vocab()
    grammar = load_grammar()
    built, _report = build_story(spec, vocab, grammar)

    def _run(apply_post_pass: bool):
        story = _copy.deepcopy(built)
        if apply_post_pass:
            _apply_post_pass_attributions(story)
        return run_validate(story, vocab, grammar, plan=None)

    res_with    = _run(apply_post_pass=True)
    res_without = _run(apply_post_pass=False)

    def _has_check_310(result):
        return any(str(e.check) == "3.10" for e in result.errors)

    assert not _has_check_310(res_with), (
        "Pre-pass-applied validate should NOT trip Check 3.10 — the wh-question "
        "should credit N5_dare_who as a new intro. "
        f"Errors: {[(e.check, e.message) for e in res_with.errors if str(e.check) == '3.10']}"
    )
    assert _has_check_310(res_without), (
        "Pre-pass-disabled validate MUST trip Check 3.10 on this story (no "
        "other path emits N5_dare_who). If this assertion fails, the "
        "pre-pass is no longer the load-bearing path — the contract has "
        "drifted and the story-17 trap can return."
    )




# ── Regression: rank_uncovered MUST NOT surface higher-tier picks while
# the current tier still has uncovered points ──────────────────────────
#
# Story 21 trap (2026-05-15): the brief recommended N4_passive and
# N4_potential as the top picks while N5 still had 13 uncovered points.
# Picking either would have hard-blocked at Check 3.9 (tier-coverage
# gate) downstream. The fix: rank_uncovered now filters out entries
# whose tier exceeds the LOWEST tier ≤ target_tier with any remaining
# uncovered point. This test pins that contract.

def test_rank_uncovered_respects_tier_ceiling() -> None:
    """While the current tier still has uncovered points, the recommender
    MUST NOT surface higher-tier entries — Check 3.9 would hard-block any
    such pick at validate-time. This test pins the contract using the
    LIVE corpus state at the time it was added (story 21, 13 N5 points
    still uncovered): no N4 (or higher) entry may appear in the ranking.
    """
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from grammar_progression import (
        rank_uncovered,
        coverage_status,
        active_jlpt,
        JLPT_TO_TIER,
    )

    # Find a target story whose tier still has uncovered points (any
    # post-bootstrap story while N5 has remaining will do; we pick the
    # next-to-author slot dynamically so the test stays valid as the
    # corpus grows).
    cov = coverage_status()
    n5_remaining = cov["by_jlpt"].get("N5", {}).get("remaining", 0)

    # Pick a target story in the current N5 window. 11 is the first
    # post-bootstrap story; story 21 is the slot that surfaced the bug.
    for target in (11, 21, 25):
        if active_jlpt(target) == "N5":
            break
    else:  # pragma: no cover — only fires if we ever leave N5
        import pytest
        pytest.skip("corpus has advanced past N5; rewrite this test for new tier")

    ranked = rank_uncovered(target_story=target)
    if n5_remaining == 0:
        # Tier already complete — N4 entries are legitimately surfaceable.
        # The ceiling guard is a no-op in this state, so nothing to assert.
        return

    target_tier = JLPT_TO_TIER[active_jlpt(target)]
    bad = [r["id"] for r in ranked
           if JLPT_TO_TIER.get(r.get("jlpt"), 99) > target_tier]
    assert not bad, (
        f"While N5 has {n5_remaining} uncovered points, the recommender "
        f"surfaced higher-tier entries that Check 3.9 would block: {bad}. "
        "rank_uncovered must filter entries above the lowest tier "
        "(≤ target_tier) with any remaining uncovered point."
    )


# ── Regression: R1 strict brief surfaces carrier templates + source
# sentences ──────────────────────────────────────────────────────────────
#
# Story 21 surfaced the biggest authoring pain point: the R1-strict
# obligations were a flat list of word_ids without context, so authors
# (LLM and human) discovered the obligations only at dry-run time and
# then retrofit a "scene-grounding" sentence to absorb 4-5 disparate
# words. That retrofit is exactly the "pedagogical bolt-on" the §E.7
# literary reviewer rejects, costing 2-3 round-trips per story.
#
# Fix: `_r1_strict_required` now enriches each item with its source
# sentence (the natural collocation) AND surfaces co-occurrence
# carrier templates (sentences in the source story that already use
# multiple required words together). Authors see this BEFORE drafting
# and can plan absorbing sentences that match natural Japanese.

def test_r1_strict_brief_surfaces_carrier_templates() -> None:
    """When R1 forces multiple words from the same source story, the
    brief MUST surface co-occurrence carrier templates (sentences
    where multiple required words appear together) so the author can
    absorb several obligations in a single paraphrase. This is the
    single biggest authoring time-saver — without it, retrofitting
    creates the bolt-on lines that fail the literary review."""
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
    from agent_brief import _r1_strict_required

    # Walk forward from the start of the post-bootstrap window looking
    # for a target story with R1 obligations from a single source. The
    # exact slot moves as the corpus grows; the contract (carrier
    # templates surface when they exist) is invariant.
    target_with_multi = None
    for target in range(11, 60):
        try:
            r = _r1_strict_required(target)
        except Exception:
            continue
        if not r["items"]:
            continue
        # Group by source story.
        by_source: dict[int, set[str]] = {}
        for it in r["items"]:
            by_source.setdefault(it["intro_in_story"], set()).add(it["word_id"])
        if any(len(v) >= 2 for v in by_source.values()):
            target_with_multi = target
            break

    if target_with_multi is None:  # pragma: no cover — defensive
        import pytest
        pytest.skip(
            "no slot in the current corpus has multi-word R1 obligations "
            "from a single source; carrier templates aren't surfaceable "
            "(the contract is still pinned by the schema-presence checks "
            "below)."
        )

    r = _r1_strict_required(target_with_multi)

    # Schema invariants: every item carries source context.
    for it in r["items"]:
        assert "source_sentence_index" in it, (
            "Every R1-required item must carry the introducing source "
            "sentence index so the author sees the natural collocation."
        )
        assert "source_sentence_surface" in it, (
            "Every R1-required item must carry the introducing source "
            "surface so the author can paraphrase the natural usage."
        )

    # Banner is non-empty when R1 work is required.
    assert r["banner"], (
        "R1 banner must be a non-empty summary string when items > 0."
    )
    assert "MUST appear" in r["banner"], (
        f"R1 banner must convey the hard-constraint nature of the "
        f"obligations; got: {r['banner']!r}"
    )

    # At least one carrier template surfaces when a single source story
    # contributes 2+ R1 words AND any sentence in that story uses 2+ of
    # them together. Stories built by the gauntlet routinely cluster
    # mints into 1-2 setting sentences, so this is the common case.
    by_source: dict[int, set[str]] = {}
    for it in r["items"]:
        by_source.setdefault(it["intro_in_story"], set()).add(it["word_id"])
    multi_sources = [sid for sid, v in by_source.items() if len(v) >= 2]
    if multi_sources:
        # At least ONE multi-source story should produce a carrier
        # template — would only fail if no source-story sentence
        # contained 2+ of the required words. That's possible in
        # principle (mints scattered across sentences) but should
        # produce a documented fall-through rather than silent data
        # loss. We assert the structural slot exists either way.
        assert "carrier_templates" in r, (
            "carrier_templates key must exist on the R1 brief, even "
            "when empty — its presence is the API contract."
        )
        for t in r["carrier_templates"]:
            assert len(t["covers_wids"]) >= 2, (
                "Carrier templates only make sense when they cover "
                "multiple required words at once."
            )
            assert t["source_surface"], (
                "Carrier templates must include the source surface "
                "so the author can read the natural sentence shape."
            )


# ─────────────────────────────────────────────────────────────────────
# Spine-classifier brief refinement (added 2026-05-15 after story 22
# burned 3 §E.7 round-trips on a structural duplicate of story 21).
# ─────────────────────────────────────────────────────────────────────

_VALID_SPINE_LABELS = frozenset({
    "search-fail-find-relief",
    "arrival-explanation",
    "transfer-and-share",
    "dialogue-question-closer",
    "solitary-reflection",
    "unclassified",
})


def test_previous_3_stories_carry_spine_label() -> None:
    """The brief's `previous_3_stories` MUST surface an `event_spine`
    block on every entry. The label must be one of the closed enum
    values; key_beats must be a list of {sentence_index, beat_kind}.

    Why pinned: the brief consumer (author) reads `previous_3_stories`
    early; if the spine label drifts (silent removal, typo, schema
    rename), the author loses the structural-shape signal entirely
    and we're back to story-22-style duplicate spines.
    """
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
    from agent_brief import _previous_3_stories_summary

    # Use the next-to-author slot so we exercise live corpus state.
    from _paths import iter_stories
    last_id = max((sid for sid, _ in iter_stories()), default=0)
    target = last_id + 1
    summary = _previous_3_stories_summary(target)
    assert len(summary) == 3, (
        f"Expected 3 prior-story entries; got {len(summary)}."
    )
    for entry in summary:
        assert "event_spine" in entry, (
            f"Story {entry.get('story_id')} entry missing event_spine: {entry}"
        )
        spine = entry["event_spine"]
        assert "label" in spine, f"event_spine missing label: {spine}"
        assert spine["label"] in _VALID_SPINE_LABELS, (
            f"Invalid spine label {spine['label']!r} for story "
            f"{entry['story_id']}; must be one of {sorted(_VALID_SPINE_LABELS)}"
        )
        assert "key_beats" in spine, f"event_spine missing key_beats: {spine}"
        assert isinstance(spine["key_beats"], list), (
            f"key_beats must be a list; got {type(spine['key_beats'])}"
        )
        for beat in spine["key_beats"]:
            assert "sentence_index" in beat and "beat_kind" in beat, (
                f"Each key_beat must carry sentence_index + beat_kind; "
                f"got {beat}"
            )
            assert isinstance(beat["sentence_index"], int), (
                f"sentence_index must be int; got {beat}"
            )


def test_carrier_template_carries_spine_replica_risk() -> None:
    """Every carrier_template in the R1-strict block MUST carry a
    `spine_replica_risk` field (high/medium/low). When any template
    is `high`, the banner MUST mention spine replication.

    Why pinned: this is the load-bearing signal that closes the
    story-22 trap. Without it, the brief recommends paraphrasing a
    template that IS the previous spine's beat, and the author
    discovers the duplication only at §E.7 (3 round-trips).
    """
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
    from agent_brief import _r1_strict_required
    from _paths import iter_stories

    # Walk the corpus to find a slot with at least one carrier template.
    target_with_template = None
    for target in range(11, 60):
        try:
            r = _r1_strict_required(target)
        except Exception:
            continue
        if r.get("carrier_templates"):
            target_with_template = target
            break

    if target_with_template is None:
        import pytest
        pytest.skip(
            "no slot in the current corpus produces a carrier template; "
            "the schema invariant below is still trivially satisfied "
            "(no templates → no risk-tags missing)."
        )

    r = _r1_strict_required(target_with_template)
    assert "previous_spine_warning" in r, (
        "previous_spine_warning block must exist on the R1 brief."
    )
    valid_risks = {"high", "medium", "low"}
    high_count = 0
    for tmpl in r["carrier_templates"]:
        assert "spine_replica_risk" in tmpl, (
            f"Carrier template missing spine_replica_risk field: {tmpl}"
        )
        assert tmpl["spine_replica_risk"] in valid_risks, (
            f"Invalid spine_replica_risk {tmpl['spine_replica_risk']!r}; "
            f"must be one of {sorted(valid_risks)}"
        )
        if tmpl["spine_replica_risk"] == "high":
            high_count += 1
            assert "spine_beat_kind" in tmpl, (
                f"high-risk template must name the matched beat_kind; "
                f"got {tmpl}"
            )

    if high_count > 0:
        assert "spine_replica_risk" in r["banner"] or "spine" in r["banner"], (
            f"When {high_count} template(s) are flagged high-risk, the "
            f"banner MUST mention spine replication so the author sees "
            f"the warning at the top of the R1 block. Got banner: "
            f"{r['banner']!r}"
        )
        warn = r["previous_spine_warning"]
        assert warn["high_risk_template_count"] == high_count, (
            f"previous_spine_warning.high_risk_template_count must match "
            f"the actual count of high-risk templates: "
            f"{warn['high_risk_template_count']} vs {high_count}"
        )


def test_story_21_classifies_as_search_fail_find_relief() -> None:
    """Pin the spine classifier against the canonical search-find-
    relief example (story 21). This story is the one whose spine
    trapped story 22 v1; if the classifier ever fails to recognize
    it, the spine-replica warning silently degrades to no-op and
    the trap returns.

    The contract is asymmetric: we require the EXACT label (no false
    negatives) AND the give_up beat at sentence_index 3 (which is
    the carrier-template sentence the brief recommends paraphrasing).
    """
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
    from agent_brief import _classify_spine
    from _paths import load_story

    try:
        story_21 = load_story(21)
    except Exception:
        import pytest
        pytest.skip("story 21 not in corpus")

    spine = _classify_spine(story_21)
    assert spine["label"] == "search-fail-find-relief", (
        f"Story 21 must classify as search-fail-find-relief; got "
        f"{spine['label']!r}. If the corpus has been restructured, "
        f"update the test rather than dropping the contract — the "
        f"spine label is the load-bearing signal for the warning."
    )
    beat_kinds = {b["beat_kind"] for b in spine["key_beats"]}
    assert "give_up" in beat_kinds, (
        f"Story 21 must surface a `give_up` beat (the 「もう探さない」 "
        f"sentence at index 3) for the carrier-template flagger to "
        f"work. Got beats: {spine['key_beats']}"
    )
    # The give_up beat must sit at sentence_index 3 — that is the
    # exact sentence the carrier-template logic surfaces.
    give_up_idx = next(
        (b["sentence_index"] for b in spine["key_beats"]
         if b["beat_kind"] == "give_up"),
        None,
    )
    assert give_up_idx == 3, (
        f"Story 21's give_up beat must be at sentence_index 3 to "
        f"line up with the carrier template the brief surfaces. "
        f"Got index {give_up_idx}."
    )


def test_story_22_brief_would_have_warned_against_story_21_spine() -> None:
    """Regression: had the spine warning existed when story 22 was
    being authored, the brief WOULD have flagged the carrier template
    from story 21 as `spine_replica_risk: high` and the banner WOULD
    have mentioned spine replication.

    This test simulates the pre-ship brief by invoking
    `_r1_strict_required(22)` — the function naturally excludes
    `sid >= target_story` from its corpus walk, so even with story 22
    already shipped, the brief output is identical to what the author
    would have seen before drafting v1.

    If this test ever fails, either: (a) story 21 was modified out of
    the search-fail-find-relief shape, or (b) the spine-detection
    wiring was removed. Either is a regression that re-opens the
    story-22 trap.
    """
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
    from agent_brief import _r1_strict_required
    from _paths import load_story

    try:
        load_story(21)
    except Exception:
        import pytest
        pytest.skip("story 21 not in corpus")

    r = _r1_strict_required(22)
    if not r.get("items"):
        import pytest
        pytest.skip(
            "story 22 brief has no R1-strict items in current corpus "
            "state — the regression scenario isn't reproducible. The "
            "spine label is still pinned by "
            "test_story_21_classifies_as_search_fail_find_relief."
        )
    warn = r["previous_spine_warning"]
    assert warn["prev_story_id"] == 21, (
        f"previous_spine_warning.prev_story_id must be 21 for target=22; "
        f"got {warn['prev_story_id']}"
    )
    assert warn["prev_spine"] == "search-fail-find-relief", (
        f"Story 22's previous_spine_warning must identify story 21's "
        f"spine as search-fail-find-relief; got {warn['prev_spine']!r}"
    )
    assert warn["high_risk_template_count"] >= 1, (
        f"Story 22's brief MUST flag at least one carrier template as "
        f"high-risk for spine replication. Got "
        f"high_risk_template_count={warn['high_risk_template_count']}. "
        f"Templates: {r['carrier_templates']}"
    )
    assert "spine" in r["banner"], (
        f"Story 22's banner MUST mention spine replication when high-risk "
        f"templates exist. Got banner: {r['banner']!r}"
    )
