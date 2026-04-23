#!/usr/bin/env python3
"""apply_recycle.py — a small helper for recycling-pass edits.

Why this exists
---------------
After designing a content swap by hand (see pipeline/recycle_planner.py),
you need to perform a sequence of bookkeeping steps that are easy to get
wrong by hand:

  1. Replace one or more sentence `tokens` arrays with a fresh design.
  2. Strip stale `audio` / `audio_hash` fields (the audio for those
     sentences is now wrong).
  3. Recompute `all_words_used` *including title and subtitle tokens*,
     in first-seen order (Check 4 of validate.py).
  4. Re-mark `is_new: true` on the first occurrence of each word_id that
     appears in the story's `new_words` list.

This helper does (2)-(4) deterministically. You provide (1) by editing
`stories/story_N.json` directly, then call:

    python pipeline/apply_recycle.py stories/story_N.json

It will rewrite the file in place. Run validate.py + recycle_planner.py
afterwards to confirm the swap landed.

Token shapes (cheat sheet)
--------------------------
- Content noun/verb/adj : {"t":"花","role":"content","r":"はな","word_id":"W00024"}
  (verbs in plain ます-form do NOT need an `inflection` block; only past
  / negative / te-form etc. do)
- Particle              : {"t":"の","role":"particle","grammar_id":"G015_no_possessive"}
- Punctuation           : {"t":"。","role":"punct"} or {"t":"、","role":"punct"}
- そして / でも            : {"t":"そして","role":"particle","grammar_id":"G012_soshite_then"}

Common grammar IDs you will reach for during recycling:
  G001_wa_topic, G002_ga_subject, G005_wo_object, G006_kara_from,
  G009_mo_also, G010_to_and, G012_soshite_then, G015_no_possessive,
  G017_de_means, G024_demo_however, G043_kosoado, etc.

If a grammar id you want isn't legal yet for the story's progression,
recycle_planner.py will not save you — pick a different word.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def first_seen_word_ids(story: dict) -> list[str]:
    used: list[str] = []
    seen: set[str] = set()
    # Title and subtitle come first per Check 4 expectations.
    for sec in ("title", "subtitle"):
        for tok in (story.get(sec) or {}).get("tokens", []):
            wid = tok.get("word_id")
            if wid and wid not in seen:
                used.append(wid)
                seen.add(wid)
    for sent in story.get("sentences", []):
        for tok in sent.get("tokens", []):
            wid = tok.get("word_id")
            if wid and wid not in seen:
                used.append(wid)
                seen.add(wid)
    return used


def strip_audio(story: dict) -> None:
    """Remove sentence-level and word-level audio fields.

    The audio is now stale for the entire story; rebuild with
    pipeline/audio_builder.py once narrative work settles.
    """
    for sent in story.get("sentences", []):
        sent.pop("audio", None)
        sent.pop("audio_hash", None)
    story.pop("word_audio", None)
    story.pop("word_audio_hash", None)


def remark_is_new(story: dict) -> None:
    """Place `is_new: true` on the first occurrence of each declared new_word.

    Called after sentence rewrites that may have moved the first occurrence
    of a recycled word. Removes stale is_new flags from later occurrences
    of words already declared.
    """
    declared = set()
    for w in story.get("new_words") or []:
        wid = w if isinstance(w, str) else (w.get("id") or w.get("word_id") or "")
        if wid:
            declared.add(wid)

    seen_first: set[str] = set()
    for sent in story.get("sentences", []):
        for tok in sent.get("tokens", []):
            wid = tok.get("word_id")
            if wid in declared and wid not in seen_first:
                tok["is_new"] = True
                seen_first.add(wid)
            elif tok.get("is_new") is True and wid not in declared:
                tok.pop("is_new", None)
            elif wid in declared and wid in seen_first:
                tok.pop("is_new", None)


def apply(path: Path) -> None:
    story = json.loads(path.read_text())
    strip_audio(story)
    remark_is_new(story)
    story["all_words_used"] = first_seen_word_ids(story)
    path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n")
    print(f"updated: {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="+", type=Path)
    args = ap.parse_args()
    for p in args.paths:
        if not p.exists():
            print(f"skip (missing): {p}", file=sys.stderr)
            continue
        apply(p)


if __name__ == "__main__":
    main()
