"""Engagement baseline integrity (catches the 'leaderboard out of date' bug class)."""
from __future__ import annotations
import json
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def baseline(root):
    p = root / "pipeline" / "engagement_baseline.json"
    if not p.exists():
        pytest.skip("no engagement baseline")
    with p.open() as f:
        return json.load(f)


def test_baseline_has_required_top_keys(baseline):
    for k in ("_meta", "reviews", "leaderboard", "next_actions"):
        assert k in baseline, f"baseline missing top-level key: {k}"


def test_review_average_matches_scores(baseline):
    bad = []
    for r in baseline["reviews"]:
        s = r.get("scores", {})
        if not s:
            continue
        computed = sum(s.values()) / len(s)
        if abs(computed - r["average"]) > 0.05:
            bad.append(f"story {r['story_id']}: average={r['average']} but mean(scores)={computed:.2f}")
    assert not bad, "\n  ".join(bad)


def test_leaderboard_covers_every_review(baseline):
    review_ids = {r["story_id"] for r in baseline["reviews"]}
    lb_ids     = {e["story_id"] for e in baseline["leaderboard"]}
    missing    = review_ids - lb_ids
    extra      = lb_ids - review_ids
    assert not missing, f"Stories with reviews but not in leaderboard: {sorted(missing)}"
    assert not extra,   f"Leaderboard entries with no review: {sorted(extra)}"


def test_leaderboard_ranks_dense_and_consistent(baseline):
    """Same average → same rank; ranks ascend with descending averages."""
    lb = baseline["leaderboard"]
    avg_by_rank: dict[int, float] = {}
    for e in lb:
        r, a = e["rank"], e["average"]
        if r in avg_by_rank and abs(avg_by_rank[r] - a) > 1e-6:
            pytest.fail(f"rank {r} has multiple averages: {avg_by_rank[r]} and {a}")
        avg_by_rank[r] = a
    # Higher rank-number ⇒ lower (or equal) average.
    sorted_ranks = sorted(avg_by_rank.items())
    for (r1, a1), (r2, a2) in zip(sorted_ranks, sorted_ranks[1:]):
        assert a1 >= a2, f"rank {r1}->{r2} has avg {a1}<{a2} (out of order)"


def test_reviews_sorted_by_story_id(baseline):
    """Predictable, scannable order. Catches future appends that break sort."""
    ids = [r["story_id"] for r in baseline["reviews"]]
    assert ids == sorted(ids), f"reviews out of order: {ids}"


def test_every_review_has_minimum_richness(baseline):
    """Each review must have at least one highlight and one weakness.
    Catches the regression I had with stories 9-10-11 (suggestions: [])."""
    bad = []
    for r in baseline["reviews"]:
        if len(r.get("highlights", [])) < 1:
            bad.append(f"story {r['story_id']}: no highlights")
        if len(r.get("weaknesses", [])) < 1:
            bad.append(f"story {r['story_id']}: no weaknesses")
    assert not bad, "\n  ".join(bad)
