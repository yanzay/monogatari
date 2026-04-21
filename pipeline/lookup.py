#!/usr/bin/env python3
"""
Quick vocab + grammar lookup for the Rovo Dev authoring loop.

Solves the "is 朝 W00015 or W00016?" / "what's the next free word_id?" /
"which grammar points are underused?" friction.

Examples:
    # Find a word by surface, kana, romaji, or English meaning
    python3 pipeline/lookup.py 朝
    python3 pipeline/lookup.py morning
    python3 pipeline/lookup.py asa

    # Show what the next available word_id and grammar_id are
    python3 pipeline/lookup.py --next

    # List grammar points by usage (helps the "give underused grammar real work" move)
    python3 pipeline/lookup.py --grammar-usage

    # Dump full record by id
    python3 pipeline/lookup.py W00015
    python3 pipeline/lookup.py G002_ga_subject

    # Find all words with occurrences < 5 (engagement reuse pool)
    python3 pipeline/lookup.py --low-occ
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
VOCAB = ROOT / "data" / "vocab_state.json"
GRAMMAR = ROOT / "data" / "grammar_state.json"
STORIES = ROOT / "stories"


def load_state() -> tuple[dict, dict]:
    return json.loads(VOCAB.read_text(encoding="utf-8")), json.loads(GRAMMAR.read_text(encoding="utf-8"))


def fmt_word(w: dict) -> str:
    occ = w.get("occurrences", 0)
    fs = w.get("first_story", "?")
    pos = w.get("pos", "?")
    cls = w.get("verb_class") or w.get("adj_class") or ""
    cls = f"/{cls}" if cls else ""
    meanings = ", ".join(w.get("meanings", []))
    return f"{w['id']:7s}  {w['surface']:6s} {w['kana']:6s} ({w.get('reading',''):8s}) {pos}{cls:6s}  occ={occ}  first=story{fs}   {meanings}"


def fmt_grammar(g: dict, usage: int = -1) -> str:
    fs = g.get("first_story", "?")
    pre = ",".join(g.get("prerequisites", []) or []) or "—"
    usage_s = f"  uses={usage}" if usage >= 0 else ""
    return f"{g['id']:24s}  {g.get('title',''):40s}  first=story{fs}  prereq={pre}{usage_s}"


def search(term: str, vocab: dict, grammar: dict) -> None:
    term_l = term.lower()
    word_hits = []
    for w in vocab["words"].values():
        if (term == w["id"]
            or term in w["surface"]
            or term in w["kana"]
            or term_l == w.get("reading", "").lower()
            or any(term_l in m.lower() for m in w.get("meanings", []))):
            word_hits.append(w)

    grammar_hits = []
    for g in grammar["points"].values():
        if (term == g["id"]
            or term_l in g.get("title", "").lower()
            or term_l in g.get("short", "").lower()
            or term in g["id"]):
            grammar_hits.append(g)

    if word_hits:
        print(f"── words ({len(word_hits)}) ──")
        for w in sorted(word_hits, key=lambda x: x["id"]):
            print(fmt_word(w))
    if grammar_hits:
        print(f"\n── grammar ({len(grammar_hits)}) ──")
        for g in sorted(grammar_hits, key=lambda x: x["id"]):
            print(fmt_grammar(g))
    if not word_hits and not grammar_hits:
        print(f"No matches for '{term}'.")


def show_next(vocab: dict, grammar: dict) -> None:
    word_ids = [int(w["id"][1:]) for w in vocab["words"].values()]
    next_word = f"W{max(word_ids)+1:05d}" if word_ids else "W00001"
    print(f"Next free word_id:    {next_word}")

    grammar_ids = [int(g["id"][1:].split("_")[0]) for g in grammar["points"].values()]
    next_grammar = f"G{max(grammar_ids)+1:03d}_<slug>" if grammar_ids else "G001_<slug>"
    print(f"Next free grammar_id: {next_grammar}")

    next_story = max(int(p.stem.split("_")[1]) for p in STORIES.glob("story_*.json")) + 1
    print(f"Next free story_id:   {next_story}")


def grammar_usage() -> None:
    vocab, grammar = load_state()
    counter = Counter()
    for path in sorted(STORIES.glob("story_*.json")):
        story = json.loads(path.read_text(encoding="utf-8"))
        for sent in story.get("sentences", []):
            for tok in sent["tokens"]:
                gid = tok.get("grammar_id")
                if gid:
                    counter[gid] += 1
                inf = tok.get("inflection")
                if inf and isinstance(inf, dict) and inf.get("grammar_id"):
                    counter[inf["grammar_id"]] += 1
    rows = []
    for gid, g in grammar["points"].items():
        rows.append((counter.get(gid, 0), g))
    rows.sort(key=lambda r: (r[0], r[1]["id"]))
    print("── grammar usage across all shipped stories (ascending) ──")
    print("(low-usage points are candidates for the 'give underused grammar real work' move.)\n")
    for usage, g in rows:
        print(fmt_grammar(g, usage=usage))


def low_occurrences() -> None:
    vocab, _ = load_state()
    rows = sorted(vocab["words"].values(), key=lambda w: (w.get("occurrences", 0), w["id"]))
    print("── words with occurrences < 5 (engagement reuse pool) ──")
    print("(Stories must keep ≥60% of content tokens drawn from this pool.)\n")
    for w in rows:
        if w.get("occurrences", 0) < 5:
            print(fmt_word(w))


def show_record(record_id: str) -> None:
    vocab, grammar = load_state()
    if record_id.startswith("W") and record_id in vocab["words"]:
        print(json.dumps(vocab["words"][record_id], ensure_ascii=False, indent=2))
        return
    if record_id.startswith("G") and record_id in grammar["points"]:
        print(json.dumps(grammar["points"][record_id], ensure_ascii=False, indent=2))
        return
    print(f"No record found for id '{record_id}'.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("term", nargs="?", help="Search term: surface, kana, romaji, English meaning, or W#####/G###_id")
    p.add_argument("--next", action="store_true", help="Show next free word_id, grammar_id, story_id")
    p.add_argument("--grammar-usage", action="store_true", help="List all grammar points sorted by usage count")
    p.add_argument("--low-occ", action="store_true", help="List words with occurrences < 5 (engagement pool)")
    p.add_argument("--jmdict", action="store_true", help="Query JMdict (English↔Japanese) for the term — useful for finding readings/POS for a candidate new word")
    p.add_argument("--morph", action="store_true", help="Run morphological analysis (UniDic-Lite) on the term — useful for verifying inflected surfaces parse the way you expect")
    args = p.parse_args()

    vocab, grammar = load_state()

    if args.next:
        show_next(vocab, grammar)
    elif args.grammar_usage:
        grammar_usage()
    elif args.low_occ:
        low_occurrences()
    elif args.jmdict and args.term:
        jmdict_search(args.term)
    elif args.morph and args.term:
        morph_analyze(args.term)
    elif args.term:
        if args.term.startswith("W") or args.term.startswith("G"):
            show_record(args.term)
        else:
            search(args.term, vocab, grammar)
    else:
        p.print_help()


def jmdict_search(term: str) -> None:
    try:
        from jp import jmdict_lookup, kana_to_romaji, JP_OK
    except Exception as e:
        print(f"jp.py unavailable: {e}")
        return
    if not JP_OK:
        print("JP toolkit (jamdict) not installed — pip install -r requirements.txt")
        return
    hits = jmdict_lookup(term, max_results=5)
    if not hits:
        print(f"No JMdict entries for '{term}'.")
        return
    print(f"── JMdict ({len(hits)} entries) for '{term}' ──")
    for i, e in enumerate(hits):
        kanji = "/".join(e.kanji) if e.kanji else "(none)"
        kana = "/".join(e.kana) if e.kana else "(none)"
        romaji = kana_to_romaji(e.kana[0]) if e.kana else ""
        print(f"\n[{i+1}] kanji={kanji}  kana={kana}  romaji={romaji}")
        for p in e.pos[:3]:
            print(f"    POS: {p}")
        for s in e.senses[:3]:
            print(f"    - {s}")


def morph_analyze(text: str) -> None:
    try:
        from jp import tokenize, JP_OK
    except Exception as e:
        print(f"jp.py unavailable: {e}")
        return
    if not JP_OK:
        print("JP toolkit (fugashi+unidic-lite) not installed — pip install -r requirements.txt")
        return
    print(f"── morphological analysis of '{text}' ──")
    print(f"{'surface':10s}  {'lemma':10s}  {'kana':12s}  {'pos':12s}  {'pos2':14s}  cForm")
    for t in tokenize(text):
        print(f"{t.surface:10s}  {t.lemma:10s}  {t.reading:12s}  {t.pos1:12s}  {t.pos2:14s}  {t.inflection_form}")


if __name__ == "__main__":
    main()
