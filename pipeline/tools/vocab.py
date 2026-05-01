#!/usr/bin/env python3
"""Searchable vocabulary inventory + occurrence lookups.

Examples:
  vocab.py search 思                       # all words containing 思
  vocab.py info W00043                     # surface, kana, meanings, occurrences
  vocab.py orphans                         # words used in 0 or 1 stories
  vocab.py orphans --max 1                 # words used in <=1 stories
  vocab.py first-occurrence W00150         # which story first uses W00150
  vocab.py would-mint "毎日"               # check if a surface would mint
  vocab.py range W00200 W00240             # show range of recently-minted vocab
"""
from __future__ import annotations
import argparse
import sys

from _common import (
    build, load_vocab, load_vocab_attributed, load_grammar, iter_stories, list_word_occurrences,
    color,
)
from _token_walk import iter_tokens


def cmd_search(args):
    vocab = load_vocab_attributed()
    needle = args.query
    hits = []
    for wid, w in vocab["words"].items():
        if (needle in (w.get("surface") or "")
                or needle in (w.get("kana") or "")
                or needle in (w.get("reading") or "")
                or any(needle.lower() in (m or "").lower() for m in (w.get("meanings") or []))):
            hits.append((wid, w))
    hits.sort(key=lambda x: int(x[0][1:]))
    for wid, w in hits:
        meaning = (w.get("meanings") or ["?"])[0][:40]
        print(f"  {color(wid,'cyan')}  {w.get('surface'):<10s} "
              f"{w.get('kana','-'):<12s} {color(meaning,'dim')}  "
              f"first={w.get('first_story','-')}  occ={w.get('occurrences',0)}")
    print(f"\n{len(hits)} match(es).")


def cmd_info(args):
    vocab = load_vocab_attributed()
    wid = args.word_id.upper()
    w = vocab["words"].get(wid)
    if not w:
        print(color(f"{wid} not found", "red")); sys.exit(1)
    print(color(f"{wid}", "cyan"), w.get("surface"))
    for k, v in w.items():
        if k == "id": continue
        print(f"  {k}: {v}")
    print()
    occ = list_word_occurrences(iter_stories(), wid)
    print(color(f"Occurrences: {len(occ)}", "bold"))
    for sid, surfaces in occ:
        print(f"  story_{sid}: {surfaces}")


def cmd_orphans(args):
    vocab = load_vocab_attributed()
    occ_by_wid: dict[str, list[tuple[int, str]]] = {wid: [] for wid in vocab["words"]}
    for sid, story in iter_stories():
        for tok in iter_tokens(story):
            wid = tok.get("word_id")
            if wid in occ_by_wid:
                occ_by_wid[wid].append((sid, tok.get("t", "?")))
    rows = []
    for wid, occ in occ_by_wid.items():
        if len(set(s for s, _ in occ)) <= args.max:
            w = vocab["words"][wid]
            meaning = (w.get("meanings") or ["?"])[0][:30]
            rows.append((int(wid[1:]), wid, w.get("surface"), meaning, len(occ),
                        sorted(set(s for s, _ in occ))))
    rows.sort()
    for _, wid, surf, mean, n, stories in rows:
        print(f"  {color(wid,'cyan')}  {surf:<10s} {color(mean,'dim'):<32s} "
              f"uses={n} stories={stories}")
    print(f"\n{len(rows)} orphan(s) (≤{args.max} story uses).")


def cmd_first(args):
    wid = args.word_id.upper()
    from _token_walk import iter_sections
    for sid, story in iter_stories():
        for section, tokens in iter_sections(story):
            for tok in tokens:
                if tok.get("word_id") == wid:
                    where = "title" if section == "title" else "sentence"
                    print(f"first occurrence of {wid}: story_{sid} ({where}: {tok.get('t')})")
                    return
    print(f"{wid}: not found in any story")


def cmd_would_mint(args):
    """Tokenize a JP surface using the converter and report which tokens would mint."""
    spec = {"story_id": 999, "title": {"jp": args.text, "en": "preview"},
            "sentences": [{"jp": args.text, "en": "preview"}]}
    vocab = load_vocab_attributed()
    grammar = load_grammar()
    story, report = build(spec, vocab, grammar)
    # The converter mutates `vocab` in-place when it mints; the report's
    # `new_words` list (a list of dicts with id+surface+meanings) is the
    # canonical, structured mint record for the spec.
    minted_records = [nw for nw in (report.get("new_words") or [])
                      if isinstance(nw, dict) and nw.get("id")]
    minted_records.sort(key=lambda r: int(r["id"][1:]))
    minted_ids = {r["id"] for r in minted_records}
    print(color(f"Tokenization of: {args.text}", "bold"))
    from _token_walk import iter_sentence_tokens
    for tok in iter_sentence_tokens(story):
        wid = tok.get("word_id", "")
        mark = color(" NEW", "red") if wid and wid in minted_ids else ""
        print(f"  {tok.get('t'):<8s} {tok.get('role','-'):<8s} "
              f"{wid or '-':<8s} {tok.get('grammar_id','-'):<20s}{mark}")
    if minted_records:
        print(color(f"\nWould mint {len(minted_records)} new word(s):", "yellow"))
        for r in minted_records:
            mean = (r.get("meanings") or ["?"])[0]
            print(f"  {r['id']}: {r.get('surface', '?')} ({mean})")
    else:
        print(color("\nNo new words minted.", "green"))


def cmd_range(args):
    vocab = load_vocab_attributed()
    lo = int(args.start.upper().lstrip("W"))
    hi = int(args.end.upper().lstrip("W"))
    for n in range(lo, hi + 1):
        wid = f"W{n:05d}"
        w = vocab["words"].get(wid)
        if not w: continue
        meaning = (w.get("meanings") or ["?"])[0][:40]
        print(f"  {color(wid,'cyan')}  {w.get('surface'):<10s} "
              f"{w.get('kana','-'):<12s} {color(meaning,'dim'):<42s} "
              f"first={w.get('first_story','-')}  occ={w.get('occurrences',0)}")


def main():
    p = argparse.ArgumentParser(prog="vocab.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="search by surface/kana/meaning substring")
    s.add_argument("query")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("info", help="full record + occurrences for a word_id")
    s.add_argument("word_id")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("orphans", help="words used in <=N stories")
    s.add_argument("--max", type=int, default=1)
    s.set_defaults(func=cmd_orphans)

    s = sub.add_parser("first-occurrence", help="which story first uses a word_id")
    s.add_argument("word_id")
    s.set_defaults(func=cmd_first)

    s = sub.add_parser("would-mint", help="dry-run a JP string and report mints")
    s.add_argument("text")
    s.set_defaults(func=cmd_would_mint)

    s = sub.add_parser("range", help="list a numeric range of word_ids")
    s.add_argument("start"); s.add_argument("end")
    s.set_defaults(func=cmd_range)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
