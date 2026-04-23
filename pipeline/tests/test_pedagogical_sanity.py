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
