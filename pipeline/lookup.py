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

    # Surface the length-progression target for the next story so the author
    # knows up front whether they're still on the plateau or stepping up.
    try:
        from progression import (
            target_sentences as _tgt_sent,
            target_content_tokens as _tgt_content,
            sentence_band as _sent_band,
            content_band as _content_band,
        )
        smin, smax = _sent_band(next_story)
        cmin, cmax = _content_band(next_story)
        print(f"Length target:        {_tgt_sent(next_story)} sentences "
              f"(band {smin}-{smax}), {_tgt_content(next_story)} content tokens "
              f"(band {cmin}-{cmax})")
        # Flag tier transitions so the author can plan accordingly.
        if next_story > 1:
            prev_sent = _tgt_sent(next_story - 1)
            this_sent = _tgt_sent(next_story)
            if this_sent != prev_sent:
                print(f"Length tier change:   story {next_story} adds +{this_sent - prev_sent} "
                      f"sentence(s) vs story {next_story - 1} (was {prev_sent})")
    except Exception:
        pass

    # Grammar tier (JLPT-aligned) for the next story
    try:
        from grammar_progression import active_tier, active_jlpt, tier_label
        gtier = active_tier(next_story)
        gjlpt = active_jlpt(next_story)
        print(f"Grammar tier:         {tier_label(gtier)} (introduce only ≤ {gjlpt} grammar)")
        # Flag JLPT tier transition between previous and current story
        if next_story > 1:
            prev_tier = active_tier(next_story - 1)
            if gtier != prev_tier:
                print(f"Grammar tier change:  story {next_story} steps up to JLPT {gjlpt} "
                      f"(was {active_jlpt(next_story - 1)})")
    except Exception:
        pass


def show_progression(up_to: int = 35) -> None:
    """Print the full length-progression curve up to the given story id."""
    try:
        from progression import progression_table
    except Exception:
        print("progression module not available")
        return
    print(f"── length progression (stories 1..{up_to}) ──\n")
    print(f"{'story':6s} {'sentences':10s} {'sent-band':10s} {'content':9s} {'content-band':14s}")
    last = None
    for r in progression_table(up_to):
        marker = "  ← +1 step" if last is not None and r["target_sentences"] != last else ""
        print(f"{r['story_id']:<6} {r['target_sentences']:<10} {str(r['sentence_band']):<10} "
              f"{r['target_content_tokens']:<9} {str(r['content_band']):<14}{marker}")
        last = r["target_sentences"]


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


def _load_catalog() -> dict:
    cat_path = Path(__file__).resolve().parent.parent / "data" / "grammar_catalog.json"
    if not cat_path.exists():
        print(f"  ⚠ {cat_path.relative_to(Path.cwd())} not found — run pipeline/build_grammar_catalog.py", file=sys.stderr)
        sys.exit(1)
    return json.loads(cat_path.read_text())


def show_catalog(jlpt_level: str) -> None:
    cat = _load_catalog()
    entries = [e for e in cat["entries"] if e["jlpt"] == jlpt_level]
    print(f"── grammar catalog: {jlpt_level} ({len(entries)} points) ──")
    print(f"  {'id':<26} {'marker':<22} {'category':<14} title")
    print(f"  {'─'*26} {'─'*22} {'─'*14} {'─'*40}")
    for e in entries:
        print(f"  {e['id']:<26} {e['marker']:<22} {e['category']:<14} {e['title']}")


def show_untaught(jlpt_level: str) -> None:
    """List grammar catalog entries at this JLPT level that haven't been
    introduced in any shipped story yet."""
    cat = _load_catalog()
    _, grammar = load_state()
    taught_catalog_ids = {
        gp.get("catalog_id")
        for gp in grammar.get("points", {}).values()
        if gp.get("catalog_id")
    }
    untaught = [
        e for e in cat["entries"]
        if e["jlpt"] == jlpt_level and e["id"] not in taught_catalog_ids
    ]
    taught = [
        e for e in cat["entries"]
        if e["jlpt"] == jlpt_level and e["id"] in taught_catalog_ids
    ]
    total = len(untaught) + len(taught)
    print(f"── untaught {jlpt_level} grammar: {len(untaught)} of {total} catalog points ──")
    print(f"  ({len(taught)} already introduced in stories)")
    print()
    by_cat: dict[str, list] = {}
    for e in untaught:
        by_cat.setdefault(e["category"], []).append(e)
    for category in sorted(by_cat):
        print(f"  ▸ {category}")
        for e in by_cat[category]:
            print(f"      {e['marker']:<22} {e['title']}")
        print()


def show_by_surface(surface: str) -> None:
    """Look up word_id(s) by exact Japanese surface."""
    vocab, _ = load_state()
    hits = [(wid, w) for wid, w in vocab.get("words", {}).items()
            if w.get("surface") == surface]
    if not hits:
        print(f"No vocab entry with surface '{surface}'.")
        print("(Tip: this might be grammar/aux/particle, not a vocab word.)")
        return
    if len(hits) == 1:
        wid, w = hits[0]
        occ = w.get("occurrences", 0)
        print(f"{wid}  {w.get('surface','')}  ({w.get('kana','')})  occ={occ}  pos={w.get('pos','?')}")
        meanings = w.get("meanings", [])
        if meanings:
            print(f"  → {', '.join(meanings)}")
    else:
        print(f"⚠ {len(hits)} homographs for '{surface}':")
        for wid, w in hits:
            occ = w.get("occurrences", 0)
            print(f"  {wid}  ({w.get('kana','')})  occ={occ}  meanings: {', '.join(w.get('meanings', []))}")


def show_reuse_preflight(spec: str) -> None:
    """
    Given a comma-separated list of word_ids (or 'wid:count' for multi-use),
    predict whether Check 6's reinforcement floor is met.

    The old percentage rule (≥ 60 % low-occ) was replaced 2026-04-22 by an
    absolute floor (≥ 6 low-occ tokens per story, or 30% of target, smaller).
    This preflight reports the count, not a percentage.

    Example:
      lookup --reuse-preflight 'W00003:3,W00028:4,W00031:2,W00043:3'
    """
    vocab, _ = load_state()
    words = vocab.get("words", {})

    plan: list[tuple[str, int]] = []
    for entry in spec.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" in entry:
            wid, count = entry.split(":", 1)
            plan.append((wid.strip(), int(count.strip())))
        else:
            plan.append((entry, 1))

    total = sum(c for _, c in plan)
    if total == 0:
        print("(empty plan)")
        return

    print(f"── Reuse preflight ({total} content tokens planned) ──")
    print(f"{'word_id':<10}{'surface':<10}{'lifetime':>10}{'plan_uses':>11}{'effective':>11}{'class':>8}")
    print("─" * 60)

    low_count = 0
    unknown_count = 0
    for wid, count in plan:
        w = words.get(wid)
        if not w:
            print(f"{wid:<10}{'?':<10}{'?':>10}{count:>11}{'?':>11}{'NEW':>8}")
            low_count += count
            unknown_count += count
            continue
        lifetime = w.get("occurrences", 0)
        effective = max(0, lifetime - count)
        cls = "LOW" if effective < 5 else "high"
        if cls == "LOW":
            low_count += count
        print(f"{wid:<10}{w.get('surface',''):<10}{lifetime:>10}{count:>11}{effective:>11}{cls:>8}")

    # Report against the new absolute floor. We don't know which story id
    # this preflight is for, so use a conservative default of 6.
    FLOOR = 6
    verdict = "✓ PASS" if low_count >= FLOOR else "✗ NEED MORE"
    print("─" * 60)
    print(f"  Low-occ tokens: {low_count} (need ≥ {FLOOR} per story)  {verdict}")
    if low_count < FLOOR:
        deficit = FLOOR - low_count
        print(f"  → Add {deficit} more low-occ token(s) to hit the reinforcement floor.")
        print(f"  → Run `lookup --low-occ` for candidates.")
    if unknown_count:
        print(f"  Note: {unknown_count} token(s) reference unknown word_id(s) — assumed new (low-occ).")


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
    p.add_argument("--progression", action="store_true", help="Print the length-progression curve up to story 35")
    p.add_argument("--grammar-progression", action="store_true", help="Print the JLPT-aligned grammar tier ladder")
    p.add_argument("--catalog", choices=["N5", "N4", "N3"], help="Print the curated grammar catalog filtered by JLPT level")
    p.add_argument("--untaught", choices=["N5", "N4", "N3"], help="List grammar points in the catalog not yet introduced in any story")
    p.add_argument("--by-surface", help="Look up word_id by exact Japanese surface (handles homographs by listing all matches)")
    p.add_argument("--reuse-preflight", help="Predict reuse-quota %% for a comma-separated list of word_ids before authoring tokens (e.g. 'W00003,W00028,W00031')")
    args = p.parse_args()

    vocab, grammar = load_state()

    if args.next:
        show_next(vocab, grammar)
    elif args.progression:
        show_progression()
    elif args.catalog:
        show_catalog(args.catalog)
        return 0
    elif args.untaught:
        show_untaught(args.untaught)
        return 0
    elif args.by_surface:
        show_by_surface(args.by_surface)
        return 0
    elif args.reuse_preflight:
        show_reuse_preflight(args.reuse_preflight)
        return 0
    elif args.grammar_progression:
        from grammar_progression import show_curve
        show_curve()
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
