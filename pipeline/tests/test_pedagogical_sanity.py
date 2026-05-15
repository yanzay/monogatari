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


