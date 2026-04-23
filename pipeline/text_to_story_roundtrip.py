#!/usr/bin/env python3
"""
text_to_story_roundtrip.py — verification gate for text_to_story.py.

For each shipped story_N.json:
  1. Extract bilingual JP+EN spec
  2. Run text_to_story.build_story on it
  3. Diff the result against the canonical story_N.json

Reports per-field diff counts, top mismatches, and exits non-zero if any
diffs remain. Used as a regression gate while iterating the converter.
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from text_to_story import build_story  # noqa


def extract_spec(canonical: dict) -> dict:
    return {
        "story_id": canonical["story_id"],
        "title":    {"jp": canonical["title"]["jp"],    "en": canonical["title"]["en"]},
        "sentences": [
            {"jp": "".join(t.get("t", "") for t in s["tokens"]), "en": s["gloss_en"]}
            for s in canonical["sentences"]
        ],
    }


# Fields stripped from canonical tokens before diff (added by audio_builder /
# state_updater AFTER conversion, so not the converter's job to produce).
POST_CONVERSION_FIELDS = {"audio_hash", "audio"}


def normalize(t: dict) -> dict:
    return {k: v for k, v in t.items() if k not in POST_CONVERSION_FIELDS}


def section_token_diff(canon_toks: list, gen_toks: list, section_name: str) -> list[dict]:
    diffs: list[dict] = []
    n = max(len(canon_toks), len(gen_toks))
    for i in range(n):
        c = canon_toks[i] if i < len(canon_toks) else None
        g = gen_toks[i]   if i < len(gen_toks)   else None
        if c is None or g is None:
            diffs.append({"section": section_name, "idx": i, "field": "presence",
                          "canon": c, "gen": g})
            continue
        c = normalize(c)
        g = normalize(g)
        for k in set(c) | set(g):
            if c.get(k) != g.get(k):
                if k == "inflection" and isinstance(c.get(k), dict) and isinstance(g.get(k), dict):
                    for ik in set(c[k]) | set(g[k]):
                        if c[k].get(ik) != g[k].get(ik):
                            diffs.append({"section": section_name, "idx": i,
                                          "field": f"inflection.{ik}",
                                          "canon": c[k].get(ik), "gen": g[k].get(ik),
                                          "surface": c.get("t")})
                else:
                    diffs.append({"section": section_name, "idx": i, "field": k,
                                  "canon": c.get(k), "gen": g.get(k),
                                  "surface": c.get("t")})
    return diffs


def diff_story(canon: dict, gen: dict) -> list[dict]:
    diffs: list[dict] = []
    diffs += section_token_diff(canon["title"]["tokens"],    gen["title"]["tokens"],    "title")
    n = max(len(canon["sentences"]), len(gen["sentences"]))
    for i in range(n):
        if i >= len(canon["sentences"]) or i >= len(gen["sentences"]):
            diffs.append({"section": f"sent{i}", "field": "presence"})
            continue
        diffs += section_token_diff(canon["sentences"][i]["tokens"],
                                    gen["sentences"][i]["tokens"], f"sent{i}")
    if canon["all_words_used"] != gen["all_words_used"]:
        diffs.append({"section": "top", "field": "all_words_used",
                      "canon_len": len(canon["all_words_used"]),
                      "gen_len":   len(gen["all_words_used"])})
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--story", type=int, default=None,
                    help="Run on a single story_id; default = all")
    ap.add_argument("--examples", type=int, default=3,
                    help="Sample mismatches to print per field (default 3)")
    ap.add_argument("--strict", action="store_true",
                    help="Exit non-zero if any diffs remain")
    args = ap.parse_args()

    vocab   = json.loads((ROOT / "data" / "vocab_state.json").read_text())
    grammar = json.loads((ROOT / "data" / "grammar_state.json").read_text())

    paths = sorted((ROOT / "stories").glob("story_*.json"),
                   key=lambda p: int(p.stem.split("_")[1]))
    if args.story is not None:
        paths = [p for p in paths if int(p.stem.split("_")[1]) == args.story]

    per_story: list[dict] = []
    field_counter: Counter = Counter()
    examples: dict[str, list] = defaultdict(list)
    errors: list[tuple[int, str]] = []

    for p in paths:
        canon = json.loads(p.read_text())
        sid = canon["story_id"]
        try:
            gen, _ = build_story(
                extract_spec(canon), vocab, grammar,
                new_word_hint=set(canon.get("new_words") or []),
                new_grammar_hint=set(canon.get("new_grammar") or []),
            )
            diffs = diff_story(canon, gen)
        except Exception as e:
            errors.append((sid, f"{type(e).__name__}: {e}"))
            continue
        per_story.append({"story_id": sid, "n_diffs": len(diffs)})
        for d in diffs:
            field_counter[d.get("field", "?")] += 1
            if "surface" in d and len(examples[d["field"]]) < args.examples:
                examples[d["field"]].append(
                    {"sid": sid, "surface": d.get("surface"),
                     "canon": d.get("canon"), "gen": d.get("gen")})

    print("=" * 60)
    print(f"text_to_story round-trip — {len(per_story)} stories")
    print("=" * 60)
    if errors:
        print(f"\nErrored: {len(errors)}")
        for sid, msg in errors[:10]:
            print(f"  story {sid:3d}: {msg}")
    perfect = sum(1 for s in per_story if s["n_diffs"] == 0)
    total_diffs = sum(s["n_diffs"] for s in per_story)
    print(f"\nZero-diff stories : {perfect} / {len(per_story)}")
    print(f"Total diffs       : {total_diffs}")
    if per_story:
        print(f"Mean / median     : {total_diffs/len(per_story):.1f} / "
              f"{sorted(s['n_diffs'] for s in per_story)[len(per_story)//2]}")

    print("\nTop diff fields:")
    for field, count in field_counter.most_common(20):
        print(f"  {count:5d}  {field}")

    if args.examples > 0 and examples:
        print("\nSample mismatches:")
        for field, exs in examples.items():
            print(f"\n  [{field}]")
            for ex in exs[:args.examples]:
                print(f"    story {ex['sid']:3d}  {ex['surface']!r}: "
                      f"canon={ex['canon']!r}  gen={ex['gen']!r}")

    if args.strict and (total_diffs > 0 or errors):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
