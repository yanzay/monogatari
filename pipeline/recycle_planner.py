#!/usr/bin/env python3
"""recycle_planner.py — surface R1/R2 reinforcement debt as actionable per-story
worklists.

Why this tool exists
--------------------
The pedagogical-sanity tests R1 (`test_vocab_words_are_reinforced`) and
R2 (`test_no_vocab_word_abandoned`) catch what is structurally a *library-wide*
problem: each story was authored in semi-isolation, so words introduced
at story_N often vanished from later stories long before the spaced-repetition
window could land them.

Fixing this requires editing many *existing* stories to weave a missed word
back in — never adding new sentences, never inflating gloss, never breaking
the existing arc. This script tells you, per story, *which word_ids you must
recycle in that story* to satisfy the rules.

Usage
-----
    python pipeline/recycle_planner.py            # human-readable summary
    python pipeline/recycle_planner.py --json     # machine-readable plan
    python pipeline/recycle_planner.py --story N  # detail for one story

Workflow for a recycle pass
---------------------------
1. Run this script with no args to see the top-loaded stories.
2. Pick ONE story you want to edit. Run with `--story N` to see the
   words it must recycle and a candidate slot-list (existing nouns the
   recycle word could replace one-for-one without changing token count).
3. Open `stories/story_N.json`, design the swaps by hand, validate with
   `pipeline/validate.py stories/story_N.json`, then rerun this script
   to confirm the deficit dropped.

Quality bar (do NOT skip)
-------------------------
- Each swap must fit the existing scene. If you cannot make 公園の木 land
  naturally because the story is set indoors, pick a different story for
  that word — don't force it.
- One-for-one content swaps (e.g., 葉 → 木の葉) are usually safest: they
  preserve sentence shape, gloss, and audio token count.
- Re-run `pipeline/state_updater.py` after each story to keep
  vocab_state.json honest, OR run the bulk rebuild snippet documented in
  NOTES_FOR_FUTURE_AGENTS.md (see "Vocab state was rebuilt from scratch").
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Keep these in lockstep with pipeline/grammar_progression.py.
VOCAB_REINFORCE_WINDOW = 10
VOCAB_REINFORCE_MIN_USES = 2
VOCAB_MAX_GAP = 20
VOCAB_ABANDON_GRACE = 10
BOOTSTRAP_END = 3

ROOT = Path(__file__).resolve().parent.parent
STORIES_DIR = ROOT / "stories"
VOCAB_PATH = ROOT / "data" / "vocab_state.json"


def load_stories() -> Dict[int, dict]:
    out: Dict[int, dict] = {}
    for f in sorted(STORIES_DIR.glob("story_*.json"),
                    key=lambda p: int(p.stem.split("_")[1])):
        s = json.loads(f.read_text())
        out[s["story_id"]] = s
    return out


def content_word_ids(story: dict) -> Set[str]:
    used: Set[str] = set()
    for sec in ("title", "subtitle"):
        for tok in (story.get(sec) or {}).get("tokens", []):
            if tok.get("role") == "content" and tok.get("word_id"):
                used.add(tok["word_id"])
    for sent in story.get("sentences", []):
        for tok in sent.get("tokens", []):
            if tok.get("role") == "content" and tok.get("word_id"):
                used.add(tok["word_id"])
    return used


def build_plan(stories: Dict[int, dict]) -> Tuple[dict, dict]:
    """Return (r1_violations, r2_violations).

    r1_violations[wid] = (deficit, candidate_target_stories, intro_story)
    r2_violations[wid] = ('trailing'|'internal', last_or_prev, trailing_or_cur, candidate_stories)
    """
    used_by = {n: content_word_ids(s) for n, s in stories.items()}
    max_n = max(stories)

    word_appearances: Dict[str, List[int]] = defaultdict(list)
    for n, ws in used_by.items():
        for w in ws:
            word_appearances[w].append(n)
    for w in word_appearances:
        word_appearances[w].sort()

    word_intro: Dict[str, int] = {}
    for n, s in stories.items():
        for w in s.get("new_words") or []:
            wid = w if isinstance(w, str) else (w.get("id") or w.get("word_id") or "")
            if wid and wid not in word_intro:
                word_intro[wid] = n

    r1: Dict[str, tuple] = {}
    for wid, intro_n in word_intro.items():
        if intro_n <= BOOTSTRAP_END:
            continue
        followups = [i for i in range(intro_n + 1, intro_n + 1 + VOCAB_REINFORCE_WINDOW)
                     if i in stories]
        if len(followups) < VOCAB_REINFORCE_MIN_USES:
            continue
        required = min(VOCAB_REINFORCE_MIN_USES, len(followups))
        hits = [i for i in followups if wid in used_by.get(i, set())]
        deficit = required - len(hits)
        if deficit > 0:
            cands = [i for i in followups if wid not in used_by.get(i, set())]
            r1[wid] = (deficit, cands, intro_n)

    r2: Dict[str, tuple] = {}
    for wid, apps in word_appearances.items():
        intro_n = word_intro.get(wid, apps[0])
        if intro_n >= max_n - VOCAB_ABANDON_GRACE + 1:
            continue
        if len(apps) < 2:
            last = apps[0]
            trailing = max_n - last
            if trailing > VOCAB_MAX_GAP:
                cands = list(range(last + 1, min(last + VOCAB_MAX_GAP + 1, max_n + 1)))
                r2[wid] = ("trailing", last, trailing, cands)
            continue
        max_gap = 0
        worst = (apps[0], apps[1])
        for prev, cur in zip(apps, apps[1:]):
            gap = cur - prev - 1
            if gap > max_gap:
                max_gap = gap
                worst = (prev, cur)
        if max_gap > VOCAB_MAX_GAP:
            prev, cur = worst
            cands = list(range(prev + 1, cur))
            r2[wid] = ("internal", prev, cur, cands)

    return r1, r2


def per_story_worklist(r1, r2, vocab) -> Dict[int, List[dict]]:
    by_target: Dict[int, List[dict]] = defaultdict(list)
    for wid, (deficit, cands, intro) in r1.items():
        surf = vocab["words"].get(wid, {}).get("surface", "?")
        pos = vocab["words"].get(wid, {}).get("pos", "?")
        for i in range(deficit):
            if i < len(cands):
                by_target[cands[i]].append({
                    "wid": wid, "surface": surf, "pos": pos,
                    "kind": "R1", "intro": intro,
                })
    for wid, (kind, prev, cur, cands) in r2.items():
        surf = vocab["words"].get(wid, {}).get("surface", "?")
        pos = vocab["words"].get(wid, {}).get("pos", "?")
        if not cands:
            continue
        # Pick the middle of the gap so a single insertion buys the most slack.
        target = cands[len(cands) // 2]
        by_target[target].append({
            "wid": wid, "surface": surf, "pos": pos,
            "kind": "R2", "intro": prev,
        })
    return by_target


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", action="store_true",
                    help="Emit machine-readable per-story plan as JSON.")
    ap.add_argument("--story", type=int,
                    help="Show detail for a single target story_id.")
    args = ap.parse_args()

    stories = load_stories()
    vocab = json.loads(VOCAB_PATH.read_text())
    r1, r2 = build_plan(stories)
    plan = per_story_worklist(r1, r2, vocab)

    if args.json:
        json.dump(
            {str(k): v for k, v in plan.items()},
            sys.stdout, ensure_ascii=False, indent=2,
        )
        return

    if args.story is not None:
        n = args.story
        items = plan.get(n, [])
        print(f"story_{n}: {len(items)} word(s) need to be woven in")
        for it in items:
            print(f"  - {it['kind']}: {it['wid']} {it['surface']} ({it['pos']}) "
                  f"— intro story_{it['intro']}")
        if not items:
            print("  (nothing scheduled here)")
        return

    print(f"R1 violations: {len(r1)} unique words "
          f"({sum(d[0] for d in r1.values())} insertions needed)")
    print(f"R2 violations: {len(r2)} unique words")
    print()
    print("Top-loaded target stories (most insertions needed):")
    for n, items in sorted(plan.items(), key=lambda kv: -len(kv[1]))[:20]:
        words = ", ".join(f"{i['surface']}({i['wid']})" for i in items[:6])
        more = f"… +{len(items)-6}" if len(items) > 6 else ""
        print(f"  story_{n:>2}: need {len(items):>2} — {words}{more}")
    print()
    print("Run with --story N for per-story detail, or --json for machine output.")


if __name__ == "__main__":
    main()
