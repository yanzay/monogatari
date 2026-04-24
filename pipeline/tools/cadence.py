#!/usr/bin/env python3
"""Run the pedagogical-cadence checks without the pytest skipif dance.

The skipif flag in pipeline/tests/test_pedagogical_sanity.py is for CI gating.
This tool always runs the underlying logic so that during authoring you get
straight answers about which weaves are needed.

Examples:
  cadence.py vocab-reinforce              # Rule R1 (must reappear ≥2 times)
  cadence.py vocab-reinforce --story 12   # only consider intros from story 12
  cadence.py vocab-abandoned              # Rule R2 — RETIRED 2026-04-24 (no-op)
  cadence.py grammar-reinforce            # Rule G2 (introduced grammar reused)
  cadence.py grammar-cadence              # Rule G1 (intro pacing)
  cadence.py vocab-cadence                # Rule V (vocab pacing)
  cadence.py all                          # everything
  cadence.py validate                     # run validate.py against the library
"""
from __future__ import annotations
import argparse
import subprocess
import sys

from _common import iter_stories, color, ROOT, PIPELINE


def _word_ids_used(story: dict) -> set[str]:
    used = set()
    for sec in ("title",):
        for tok in (story.get(sec) or {}).get("tokens", []):
            if tok.get("word_id"):
                used.add(tok["word_id"])
    for sn in story.get("sentences", []):
        for tok in sn.get("tokens", []):
            if tok.get("word_id"):
                used.add(tok["word_id"])
    return used


def _grammar_ids_used(story: dict) -> set[str]:
    used = set()
    for sec in ("title",):
        for tok in (story.get(sec) or {}).get("tokens", []):
            if tok.get("grammar_id"):
                used.add(tok["grammar_id"])
    for sn in story.get("sentences", []):
        for tok in sn.get("tokens", []):
            if tok.get("grammar_id"):
                used.add(tok["grammar_id"])
    return used


def _by_n() -> dict[int, dict]:
    return {sid: story for sid, story in iter_stories()}


def cmd_vocab_reinforce(args):
    sys.path.insert(0, str(PIPELINE))
    from grammar_progression import (BOOTSTRAP_END,
                                     VOCAB_REINFORCE_WINDOW,
                                     VOCAB_REINFORCE_MIN_USES)
    by_n = _by_n()
    used = {n: _word_ids_used(s) for n, s in by_n.items()}
    intros = {}
    for n, s in by_n.items():
        if n <= BOOTSTRAP_END: continue
        ids = [w if isinstance(w, str) else w.get("id") or w.get("word_id", "")
               for w in (s.get("new_words") or [])]
        intros[n] = [i for i in ids if i]
    bad = []
    for n, ids in intros.items():
        if args.story and n != args.story: continue
        followups = [i for i in range(n+1, n+1+VOCAB_REINFORCE_WINDOW) if i in by_n]
        if len(followups) < VOCAB_REINFORCE_MIN_USES: continue
        required = min(VOCAB_REINFORCE_MIN_USES, len(followups))
        for wid in ids:
            hits = [i for i in followups if wid in used.get(i, set())]
            if len(hits) < required:
                bad.append((n, wid, len(hits), len(followups), hits))
    if not bad:
        print(color(f"✓ Rule R1: all introduced vocab reinforced ≥2 times.", "green"))
        return
    for n, wid, h, w, hits in bad:
        print(f"  {color(f'story_{n}','yellow')} W={color(wid,'cyan')} "
              f"reappears in {h}/{w} stories (saw {hits or 'none'})")
    print(f"\n{color(f'{len(bad)} Rule R1 violation(s)','red')}")


def cmd_vocab_abandoned(args):
    """Rule R2 — RETIRED 2026-04-24. See test_no_vocab_word_abandoned."""
    print(color(
        "ℹ Rule R2 (vocab abandonment) is retired. The library no longer\n"
        "  enforces a max gap between consecutive uses of a word past its\n"
        "  initial maturation window. Late reuse is encouraged but not required.\n"
        "  Rule R1 (cmd_vocab_reinforce) still enforces ≥2 uses within the\n"
        "  10-story window after introduction.",
        "yellow"))


def cmd_grammar_reinforce(args):
    sys.path.insert(0, str(PIPELINE))
    from grammar_progression import REINFORCEMENT_WINDOW, MIN_REINFORCEMENT_USES
    by_n = _by_n()
    used = {n: _grammar_ids_used(s) for n, s in by_n.items()}
    intros = {}
    for n, s in by_n.items():
        ids = [g if isinstance(g, str) else g.get("id") for g in (s.get("new_grammar") or [])]
        intros[n] = [i for i in ids if i]
    bad = []
    for n, ids in intros.items():
        followups = [i for i in range(n+1, n+1+REINFORCEMENT_WINDOW) if i in by_n]
        if not followups: continue
        required = min(MIN_REINFORCEMENT_USES, len(followups))
        for gid in ids:
            hits = [i for i in followups if gid in used.get(i, set())]
            if len(hits) < required:
                bad.append((n, gid, len(hits), len(followups), hits))
    if not bad:
        print(color("✓ Rule G2: all introduced grammar reinforced.", "green")); return
    for n, gid, h, w, hits in bad:
        print(f"  story_{n} {color(gid,'cyan')} reappears in {h}/{w}  saw={hits or 'none'}")
    print(f"\n{color(f'{len(bad)} Rule G2 violation(s)','red')}")


def cmd_validate(args):
    by_n = _by_n()
    bad = []
    for sid in sorted(by_n):
        r = subprocess.run([sys.executable, "pipeline/validate.py", f"stories/story_{sid}.json"],
                           capture_output=True, text=True, cwd=ROOT)
        if "✓" not in r.stdout.split("\n")[0]:
            bad.append((sid, r.stdout))
    if not bad:
        print(color(f"✓ All {len(by_n)} stories validate cleanly.", "green")); return
    for sid, out in bad:
        print(color(f"✗ story_{sid}", "red"))
        for line in out.splitlines():
            if "Check" in line or "error" in line.lower():
                print(f"    {line}")
    print(f"\n{color(f'{len(bad)} invalid story(ies)','red')}")


def cmd_all(args):
    print(color("=== Rule R1 (vocab early reinforcement) ===", "bold"))
    cmd_vocab_reinforce(args)
    print()
    print(color("=== Rule R2 (vocab abandonment) ===", "bold"))
    cmd_vocab_abandoned(args)
    print()
    print(color("=== Rule G2 (grammar reinforcement) ===", "bold"))
    cmd_grammar_reinforce(args)
    print()
    print(color("=== Validator ===", "bold"))
    cmd_validate(args)


def main():
    p = argparse.ArgumentParser(prog="cadence.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in [("vocab-reinforce", cmd_vocab_reinforce),
                     ("vocab-abandoned", cmd_vocab_abandoned),
                     ("grammar-reinforce", cmd_grammar_reinforce),
                     ("validate", cmd_validate),
                     ("all", cmd_all)]:
        s = sub.add_parser(name)
        s.add_argument("--story", type=int, default=None,
                       help="restrict to violations whose intro is in this story")
        s.set_defaults(func=fn)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
