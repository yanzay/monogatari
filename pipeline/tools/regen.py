#!/usr/bin/env python3
"""Incremental story regeneration with optional dry-run / diff modes.

Wraps pipeline/regenerate_all_stories.py but exposes single-story modes
that skip the full library loop when you only changed one spec.

Examples:
  regen.py story 18              # regen story 18 only (rest of library untouched)
  regen.py all                   # equivalent to regenerate_all_stories.py --apply
  regen.py validate              # validate every shipped story without writing
  regen.py diff 18               # show what would change without writing
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path

from _common import (load_spec, load_vocab, load_grammar, load_story,
                     iter_stories, build, ROOT, STORIES, color)
# `validate` is imported lazily inside cmd_validate so other commands stay
# fast (validate.py pulls in jp.py + fugashi at import time).


def cmd_story(args):
    """Regenerate a single story_N.json + the library-wide first-occurrence pass.

    NOTE: because the first-occurrence pass is library-wide, regenerating a
    single story can shift `is_new` flags on later stories. We therefore
    fall back to the full regenerator when --safe is not passed.
    """
    sid = args.story_id
    if not args.unsafe:
        # Full regeneration is needed to keep first-occurrence consistent
        return _full_regen()
    spec = load_spec(sid)
    vocab = load_vocab(); grammar = load_grammar()
    story, report = build(spec, vocab, grammar)
    out = STORIES / f"story_{sid}.json"
    out.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n")
    print(color(f"✓ wrote {out}  (UNSAFE: skipped first-occurrence pass)", "yellow"))


def _full_regen():
    r = subprocess.run([sys.executable, "pipeline/regenerate_all_stories.py", "--apply"],
                       cwd=ROOT, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    return r.returncode


def cmd_all(args):
    return _full_regen()


def cmd_validate(args):
    """In-process library validation — ~50× faster than per-story subprocesses."""
    from validate import validate as _validate
    vocab = load_vocab(); grammar = load_grammar()
    bad = []
    for sid, story in iter_stories():
        result = _validate(story, vocab, grammar, plan=None)
        if not result.valid:
            bad.append((sid, result))
    if not bad:
        print(color("✓ All stories validate cleanly.", "green")); return
    for sid, result in bad:
        print(color(f"✗ story_{sid}", "red"))
        for e in result.errors:
            print(f"    Check {e.check}: {e.location}: {e.message}" if e.location
                  else f"    Check {e.check}: {e.message}")
    print(color(f"\n{len(bad)} invalid story(ies)", "red"))
    sys.exit(1)


def cmd_diff(args):
    sid = args.story_id
    spec = load_spec(sid)
    vocab = load_vocab(); grammar = load_grammar()
    new_story, _ = build(spec, vocab, grammar)
    old_story = load_story(sid)
    old_n = len(old_story.get("sentences", []))
    new_n = len(new_story.get("sentences", []))
    if old_n != new_n:
        print(color(f"sentence count: {old_n} → {new_n}", "yellow"))
    old_words = {w if isinstance(w, str) else w.get("id") for w in (old_story.get("new_words") or [])}
    new_words = set()
    for w in new_story.get("new_words") or []:
        new_words.add(w if isinstance(w, str) else (w.get("id") if isinstance(w, dict) else None))
    if old_words != new_words:
        print(color(f"new_words: -{old_words-new_words} +{new_words-old_words}", "yellow"))
    print(color("(NOTE: this diff doesn't run the library-wide first-occurrence "
                "pass, so is_new/new_words/new_grammar may differ from a real "
                "regen. Use it for token-shape sanity checks.)", "dim"))


def main():
    p = argparse.ArgumentParser(prog="regen.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("story", help="regenerate the whole library (single-story is unsafe)")
    s.add_argument("story_id", type=int)
    s.add_argument("--unsafe", action="store_true",
                   help="skip the full library regen — fast but may break is_new flags")
    s.set_defaults(func=cmd_story)

    s = sub.add_parser("all", help="full library regen")
    s.set_defaults(func=cmd_all)

    s = sub.add_parser("validate", help="validate every shipped story")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("diff", help="show what regenerating one story would change")
    s.add_argument("story_id", type=int)
    s.set_defaults(func=cmd_diff)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
