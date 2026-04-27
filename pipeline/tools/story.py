#!/usr/bin/env python3
"""Per-story introspection.

Examples:
  story.py info 18                # title, sentence count, intros, target band
  story.py intros 18              # words/grammar that this story introduces
  story.py uses 18                # all word_ids and grammar_ids appearing in story 18
  story.py band 18                # show its progression band (target, low, high)
  story.py contains W00043        # which sentence indices contain a word_id
  story.py contains G016 --story 18
"""
from __future__ import annotations
import argparse
import sys

from _common import (load_story, load_vocab, load_grammar, iter_stories,
                     ROOT, PIPELINE, color)
from _token_walk import iter_sections, word_ids_used, grammar_ids_used


def _band(sid: int):
    sys.path.insert(0, str(PIPELINE))
    from progression import (target_sentences, target_content_tokens,
                             SENTENCE_TOLERANCE, CONTENT_LOW, CONTENT_HIGH)
    t_sent = target_sentences(sid)
    t_tok = target_content_tokens(sid)
    return {
        "target_sentences": t_sent,
        "sentence_band": (max(2, t_sent - SENTENCE_TOLERANCE), t_sent + SENTENCE_TOLERANCE),
        "target_content_tokens": t_tok,
        "content_band": (int(t_tok * CONTENT_LOW), int(t_tok * CONTENT_HIGH)),
    }


def cmd_info(args):
    sid = args.story_id
    s = load_story(sid)
    band = _band(sid)
    n_sent = len(s.get("sentences", []))
    n_tok = sum(1 for sn in s.get("sentences", [])
                for t in sn.get("tokens", []) if t.get("role") == "content")
    print(color(f"story_{sid}", "bold"), "—",
          s.get("title", {}).get("jp", "?"), "/", s.get("title", {}).get("en", "?"))
    print(f"  sentences: {n_sent} (target {band['target_sentences']}, "
          f"band {band['sentence_band']})")
    print(f"  content tokens: {n_tok} (target {band['target_content_tokens']}, "
          f"band {band['content_band']})")
    nw = s.get("new_words") or []
    ng = s.get("new_grammar") or []
    print(f"  introduces: {len(nw)} word(s), {len(ng)} grammar")
    if nw: print(f"    words: {nw}")
    if ng: print(f"    grammar: {ng}")


def cmd_intros(args):
    sid = args.story_id
    s = load_story(sid)
    vocab = load_vocab(); grammar = load_grammar()
    nw = s.get("new_words") or []
    ng = s.get("new_grammar") or []
    if nw:
        print(color("New words:", "bold"))
        for w in nw:
            wid = w if isinstance(w, str) else w.get("id")
            rec = vocab["words"].get(wid, {})
            mean = (rec.get("meanings") or ["?"])[0][:40]
            print(f"  {color(wid,'cyan')}  {rec.get('surface','?'):<10s} "
                  f"{rec.get('kana','-'):<12s} {color(mean,'dim')}")
    if ng:
        print(color("New grammar:", "bold"))
        for g in ng:
            gid = g if isinstance(g, str) else g.get("id")
            rec = grammar["points"].get(gid, {})
            print(f"  {color(gid,'cyan')}  {rec.get('title','?')}")
    if not nw and not ng:
        print(color("(no new vocab or grammar introduced)", "dim"))


def cmd_uses(args):
    sid = args.story_id
    s = load_story(sid)
    wids = word_ids_used(s)
    # Match historical behaviour: count only direct grammar_id, not inflection.
    gids = grammar_ids_used(s, include_inflection=False)
    print(color(f"story_{sid} uses:", "bold"))
    print(f"  {len(wids)} word(s): {sorted(wids)}")
    print(f"  {len(gids)} grammar: {sorted(gids)}")


def cmd_band(args):
    sid = args.story_id
    band = _band(sid)
    print(color(f"story_{sid} progression band:", "bold"))
    for k, v in band.items():
        print(f"  {k}: {v}")


def cmd_contains(args):
    needle = args.id.upper()
    is_grammar = needle.startswith("G")
    target_field = "grammar_id" if is_grammar else "word_id"
    if args.story:
        targets = [(args.story, load_story(args.story))]
    else:
        targets = list(iter_stories())
    for sid, s in targets:
        for section, tokens in iter_sections(s):
            # section is 'title' or 'sentence_<i>'; render the latter as 's<i>'.
            label = section if section == "title" else "s" + section.split("_", 1)[1]
            for ti, tok in enumerate(tokens):
                if tok.get(target_field) == needle:
                    print(f"  story_{sid}:{label}:{ti}  {tok.get('t')}")


def main():
    p = argparse.ArgumentParser(prog="story.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("info"); s.add_argument("story_id", type=int); s.set_defaults(func=cmd_info)
    s = sub.add_parser("intros"); s.add_argument("story_id", type=int); s.set_defaults(func=cmd_intros)
    s = sub.add_parser("uses"); s.add_argument("story_id", type=int); s.set_defaults(func=cmd_uses)
    s = sub.add_parser("band"); s.add_argument("story_id", type=int); s.set_defaults(func=cmd_band)
    s = sub.add_parser("contains"); s.add_argument("id")
    s.add_argument("--story", type=int, default=None)
    s.set_defaults(func=cmd_contains)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
