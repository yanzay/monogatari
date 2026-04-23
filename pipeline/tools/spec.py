#!/usr/bin/env python3
"""Surgical bilingual-spec editor.

Operates directly on pipeline/inputs/story_N.bilingual.json. Run
`pipeline/tools/regen.py story N` afterwards to refresh stories/story_N.json.

Examples:
  spec.py show 18                              # pretty-print spec
  spec.py append 18 --jp "..." --en "..."     # append a sentence
  spec.py replace 18:5 --jp "..." --en "..."  # replace sentence index 5
  spec.py delete 18:5                          # delete sentence index 5
  spec.py move 18:5 --to 18:8                  # move sentence within a story
  spec.py find "鞄"                            # all stories using a JP substring
  spec.py title 18 --jp "..." --en "..."      # change a title
"""
from __future__ import annotations
import argparse
import sys

from _common import (load_spec, save_spec, iter_specs, mint_check, color)


def _check_mint(jp: str, allow_mint: bool) -> None:
    """Abort the operation if the sentence would mint, unless --allow-mint."""
    mints = mint_check(jp)
    if mints and not allow_mint:
        print(color(f"✗ This sentence would mint {len(mints)} new word(s):", "red"))
        for nw in mints:
            print(f"    {nw}")
        print(color("    Re-run with --allow-mint to proceed anyway, or use "
                    "vocab.py search to find existing equivalents.", "yellow"))
        sys.exit(2)
    if mints:
        print(color(f"⚠ Allowing {len(mints)} mint(s):", "yellow"))
        for nw in mints:
            print(f"    {nw}")


def parse_locator(arg: str) -> tuple[int, int | None]:
    """Accept '18' or '18:5' → (18, 5) or (18, None)."""
    if ":" in arg:
        a, b = arg.split(":", 1)
        return int(a), int(b)
    return int(arg), None


def cmd_show(args):
    sid, _ = parse_locator(args.locator)
    s = load_spec(sid)
    print(color(f"story_{sid}: {s.get('title',{}).get('jp')}  /  "
                f"{s.get('title',{}).get('en')}", "bold"))
    for i, sn in enumerate(s.get("sentences", [])):
        print(f"  {i:2d}: {sn['jp']}")
        print(f"      {color(sn['en'],'dim')}")


def cmd_append(args):
    sid, _ = parse_locator(args.locator)
    _check_mint(args.jp, args.allow_mint)
    s = load_spec(sid)
    s.setdefault("sentences", []).append({"jp": args.jp, "en": args.en})
    save_spec(sid, s)
    print(color(f"✓ appended to story_{sid} (now {len(s['sentences'])} sentences)", "green"))


def cmd_replace(args):
    sid, idx = parse_locator(args.locator)
    if idx is None:
        sys.exit("replace requires N:I (e.g. 18:5)")
    _check_mint(args.jp, args.allow_mint)
    s = load_spec(sid)
    if not (0 <= idx < len(s.get("sentences", []))):
        sys.exit(f"index {idx} out of range (have {len(s.get('sentences', []))} sentences)")
    old = s["sentences"][idx]
    s["sentences"][idx] = {"jp": args.jp, "en": args.en}
    save_spec(sid, s)
    print(color(f"✓ replaced story_{sid}:{idx}", "green"))
    print(f"   was: {old['jp']}")
    print(f"   now: {args.jp}")


def cmd_delete(args):
    sid, idx = parse_locator(args.locator)
    if idx is None:
        sys.exit("delete requires N:I (e.g. 18:5)")
    s = load_spec(sid)
    if not (0 <= idx < len(s.get("sentences", []))):
        sys.exit(f"index {idx} out of range")
    removed = s["sentences"].pop(idx)
    save_spec(sid, s)
    print(color(f"✓ deleted story_{sid}:{idx}: {removed['jp']}", "green"))


def cmd_move(args):
    sid, idx = parse_locator(args.locator)
    if idx is None:
        sys.exit("move requires N:I as source")
    dst_sid, dst_idx = parse_locator(args.to)
    if dst_idx is None:
        sys.exit("--to requires N:I")
    if sid != dst_sid:
        sys.exit("cross-story move not supported (do delete+append manually)")
    s = load_spec(sid)
    if not (0 <= idx < len(s.get("sentences", []))):
        sys.exit(f"src index {idx} out of range")
    sn = s["sentences"].pop(idx)
    s["sentences"].insert(dst_idx, sn)
    save_spec(sid, s)
    print(color(f"✓ moved story_{sid}:{idx} → story_{sid}:{dst_idx}", "green"))


def cmd_find(args):
    needle = args.text
    n_hits = 0
    for sid, s in iter_specs():
        for i, sn in enumerate(s.get("sentences", [])):
            if needle in sn["jp"]:
                print(f"  story_{sid}:{i}  {sn['jp']}")
                n_hits += 1
        for sec_name in ("title",):
            sec = s.get(sec_name) or {}
            if needle in (sec.get("jp") or ""):
                print(f"  story_{sid}:{sec_name}  {sec['jp']}")
                n_hits += 1
    print(f"\n{n_hits} match(es).")


def cmd_title(args):
    sid, _ = parse_locator(args.locator)
    s = load_spec(sid)
    s["title"] = {"jp": args.jp, "en": args.en}
    save_spec(sid, s)
    print(color(f"✓ updated story_{sid} title", "green"))


def main():
    p = argparse.ArgumentParser(prog="spec.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("show"); s.add_argument("locator"); s.set_defaults(func=cmd_show)

    s = sub.add_parser("append"); s.add_argument("locator")
    s.add_argument("--jp", required=True); s.add_argument("--en", required=True)
    s.add_argument("--allow-mint", action="store_true",
                   help="proceed even if the sentence would mint a new word_id")
    s.set_defaults(func=cmd_append)

    s = sub.add_parser("replace"); s.add_argument("locator")
    s.add_argument("--jp", required=True); s.add_argument("--en", required=True)
    s.add_argument("--allow-mint", action="store_true",
                   help="proceed even if the sentence would mint a new word_id")
    s.set_defaults(func=cmd_replace)

    s = sub.add_parser("delete"); s.add_argument("locator"); s.set_defaults(func=cmd_delete)

    s = sub.add_parser("move"); s.add_argument("locator")
    s.add_argument("--to", required=True); s.set_defaults(func=cmd_move)

    s = sub.add_parser("find"); s.add_argument("text"); s.set_defaults(func=cmd_find)

    s = sub.add_parser("title"); s.add_argument("locator")
    s.add_argument("--jp", required=True); s.add_argument("--en", required=True)
    s.set_defaults(func=cmd_title)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
