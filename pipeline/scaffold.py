#!/usr/bin/env python3
"""
Scaffold a fresh pipeline/plan.json or pipeline/story_raw.json with all
required fields populated and the next-free ids pre-filled.

Solves the field-name-drift, missing-required-field, and ID-confusion friction
that's most expensive at the start of an authoring session.

Usage:
    # Generate a plan skeleton for the next story
    python3 pipeline/scaffold.py plan --title-jp 猫 --title-en "The Cat" \\
        --new-words 2 --new-grammar 0

    # Generate a story_raw.json skeleton aligned to a plan
    python3 pipeline/scaffold.py story --sentences 7

The output is intentionally a skeleton — the author fills in:
  * theme, setting, constraints (plan)
  * the new word/grammar definition fields the schema requires
  * the actual sentence tokens (story_raw)

But the structure is correct, so the author cannot accidentally drop a
required field.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "pipeline" / "plan.json"
STORY_RAW = ROOT / "pipeline" / "story_raw.json"
VOCAB = ROOT / "data" / "vocab_state.json"
GRAMMAR = ROOT / "data" / "grammar_state.json"
STORIES = ROOT / "stories"


def load_state() -> tuple[dict, dict, int, str, str]:
    vocab = json.loads(VOCAB.read_text(encoding="utf-8"))
    grammar = json.loads(GRAMMAR.read_text(encoding="utf-8"))
    word_ids = [int(w["id"][1:]) for w in vocab["words"].values()]
    next_word = f"W{(max(word_ids)+1):05d}" if word_ids else "W00001"
    grammar_ids = [int(g["id"][1:].split("_")[0]) for g in grammar["points"].values()]
    next_grammar = f"G{(max(grammar_ids)+1):03d}" if grammar_ids else "G001"
    next_story = (max((int(p.stem.split("_")[1]) for p in STORIES.glob("story_*.json")), default=0) + 1)
    return vocab, grammar, next_story, next_word, next_grammar


def _enrich_word_from_jmdict(surface: str | None) -> dict | None:
    """Build a new_word_definition skeleton for a single surface.

    Strategy:
      1. If the surface looks like a verb (fugashi tokenizes it as 動詞 or
         it's a noun+する compound), use jp.analyze_verb() — UniDic-backed,
         handles every conjugation class including irregulars and
         suru-compounds. JMdict is consulted only for meanings.
      2. Otherwise (nouns, adjectives, particles, etc.), fall back to
         direct JMdict lookup.

    Returns None if jp.py is unavailable.
    """
    if not surface:
        return None
    try:
        from jp import jmdict_lookup, derive_kana, kana_to_romaji, analyze_verb, JP_OK
    except Exception:
        return None
    if not JP_OK:
        return None

    # ── Step 1: verb path (fugashi-first) ────────────────────────────────
    verb_info = analyze_verb(surface)
    if verb_info is not None:
        # Pull a meaning from JMdict — try the lemma first (the dictionary
        # form is what JMdict actually indexes), then fall back to surface.
        lemma_hits = jmdict_lookup(verb_info["lemma"], max_results=1)
        surface_hits = jmdict_lookup(surface, max_results=1) if not lemma_hits else []
        h = (lemma_hits or surface_hits or [None])[0]
        meaning = (h.senses[0] if (h and h.senses) else "<primary English meaning>")
        # Suru-compound meaning synthesis: if analyze_verb returned
        # irregular_suru with a non-trivial prefix (e.g. 勉強する), JMdict
        # almost certainly has no entry for the compound — but it does for
        # the noun half. JMdict tags suru-capable nouns with "vs" (短縮)
        # POS; when we find one, synthesize "to <first_sense>" as the
        # verb meaning. e.g. 勉強する → "to study", 散歩する → "to take a walk".
        if verb_info["verb_class"] == "irregular_suru":
            for tail in ("する", "為る"):
                if verb_info["lemma"].endswith(tail):
                    noun = verb_info["lemma"][: -len(tail)]
                    break
            else:
                noun = ""
            if noun and (not h or not h.senses):
                noun_hits = jmdict_lookup(noun, max_results=1)
                if noun_hits:
                    nh = noun_hits[0]
                    pos_str = " ".join(nh.pos).lower()
                    is_vs = ("vs" in pos_str.split()) or ("takes the auxiliary verb suru" in pos_str)
                    if nh.senses:
                        # JMdict often packs multiple synonyms into a single
                        # "sense" string separated by ";" — only prefix "to "
                        # to the first synonym to avoid "to cooking; cookery;
                        # cuisine; ...".
                        first_sense = nh.senses[0]
                        head, _, tail = first_sense.partition(";")
                        head = head.strip()
                        # Convert obvious -ing nominalizations to bare verbs:
                        # "cooking" → "cook", "cleaning" → "clean".
                        # Only do this when the noun pattern is single-word -ing
                        # (multi-word phrases like "physical training" stay as-is).
                        if head and " " not in head and head.lower().endswith("ing") and len(head) > 4:
                            base_word = head[:-3]
                            # Restore final 'e' for stems that look like they
                            # need it (cleaning → clean, not "clean"; making → make).
                            # We don't try to be clever — just emit both spellings
                            # joined by " / " so the author can pick.
                            head_verb = base_word
                            head = head_verb
                        if head.lower().startswith("to "):
                            meaning = head
                        else:
                            meaning = f"to {head}"
        # For polite-form input use masu_kana; otherwise lemma_kana.
        kana_out = verb_info["masu_kana"] if verb_info["is_polite"] else verb_info["lemma_kana"]
        return {
            "surface": surface,
            "kana": kana_out,
            "reading": kana_to_romaji(kana_out),
            "pos": "verb",
            "verb_class": verb_info["verb_class"],
            "adj_class": None,
            "meanings": [meaning],
            "_jmdict_pos": (
                f"{verb_info['conj_type']} → {verb_info['verb_class']} "
                f"(via fugashi; lemma={verb_info['lemma']})"
            ),
        }

    # ── Step 2: non-verb path (JMdict direct) ────────────────────────────
    hits = jmdict_lookup(surface, max_results=1)
    if not hits:
        return None
    h = hits[0]
    kana = (h.kana[0] if h.kana else (derive_kana(surface) or surface)) or surface
    pos_label = (h.pos[0].lower() if h.pos else "")
    if "adjective" in pos_label and ("i-" in pos_label or "(keiyoushi)" in pos_label):
        pos, vclass = "adjective", None
    elif "adjective" in pos_label or "na-adjective" in pos_label:
        pos, vclass = "adjective", None
    elif "noun" in pos_label or "名詞" in pos_label:
        pos, vclass = "noun", None
    else:
        pos, vclass = "noun", None

    return {
        "surface": surface,
        "kana": kana,
        "reading": kana_to_romaji(kana),
        "pos": pos,
        "verb_class": vclass,
        "adj_class": "i" if "i-" in pos_label else ("na" if "na-" in pos_label else None) if pos == "adjective" else None,
        "meanings": [h.senses[0]] if h.senses else ["<primary English meaning>"],
        "_jmdict_pos": pos_label,  # diagnostic; you can delete this before shipping
    }


def scaffold_plan(args) -> int:
    vocab, grammar, next_story, next_word, next_grammar = load_state()
    new_words = []
    new_word_defs = {}
    nw_int = int(next_word[1:])
    surfaces = (args.new_word_surfaces or "").split(",") if args.new_word_surfaces else []
    surfaces = [s.strip() for s in surfaces if s.strip()]
    for i in range(args.new_words):
        wid = f"W{nw_int + i:05d}"
        new_words.append(wid)
        surface = surfaces[i] if i < len(surfaces) else None
        enriched = _enrich_word_from_jmdict(surface) if surface else None
        if enriched:
            new_word_defs[wid] = {
                "id": wid,
                "first_story": next_story,
                "grammar_tags": [],
                **enriched,
            }
        else:
            new_word_defs[wid] = {
                "id": wid,
                "surface": surface or "<kanji or kana>",
                "kana": "<hiragana>",
                "reading": "<romaji>",
                "pos": "<noun|verb|adjective|adverb|pronoun>",
                "verb_class": None,
                "adj_class": None,
                "meanings": ["<primary English meaning>"],
                "first_story": next_story,
                "grammar_tags": []
            }

    new_grammar = []
    new_grammar_defs = {}
    ng_int = int(next_grammar[1:])
    for i in range(args.new_grammar):
        gid = f"G{ng_int + i:03d}_<slug>"
        new_grammar.append(gid)
        new_grammar_defs[gid] = {
            "id": gid,
            "title": "<particle/form> — short pedagogical title",
            "short": "<one-sentence rule>",
            "long": "<paragraph: when to use, how it contrasts with related grammar, common pitfalls>",
            "genki_ref": "L?",
            "prerequisites": []
        }

    # Suggest 5 lowest-occurrence words as candidates for must_reuse
    low = sorted(vocab["words"].values(), key=lambda w: (w.get("occurrences", 0), w["id"]))
    must_reuse = [w["id"] for w in low[:5]]

    # Pull progression targets so the scaffold pre-fills the right numbers.
    try:
        from progression import (
            target_sentences as _tgt_sent,
            target_content_tokens as _tgt_content,
            sentence_band as _sent_band,
        )
        tgt_sentences = _tgt_sent(next_story)
        tgt_content_tokens = _tgt_content(next_story)
        _, smax = _sent_band(next_story)
    except Exception:
        tgt_sentences, tgt_content_tokens, smax = 7, 18, 8

    plan = {
        "story_id": next_story,
        "title_jp": args.title_jp or "<title in Japanese>",
        "title_en": args.title_en or "<title in English>",
        "subtitle_jp": args.subtitle_jp or "<subtitle in Japanese>",
        "subtitle_en": args.subtitle_en or "<subtitle in English>",
        "theme": "<2-5 sentence theme: what the story is *about*, the central feeling, the small surprise>",
        "setting": "<one or two sentences: where, when, who is present>",
        "constraints": {
            "must_reuse_words": must_reuse,
            "forbidden_words": [],
            "avoid_topics": ["violence", "romance", "politics"]
        },
        "target_word_count": tgt_content_tokens,
        "max_sentences": smax,
        "new_words": new_words,
        "new_word_definitions": new_word_defs,
        "new_grammar": new_grammar,
        "new_grammar_definitions": new_grammar_defs,
        "context_words_to_reuse": must_reuse,
        "notes": "<authoring notes: which engagement moves the story will make, which underused grammar gets work, the planned hook + closer>"
    }

    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✓ Wrote {PLAN.relative_to(ROOT)}  (story_id={next_story})")
    print(f"  next_word_id starts at {next_word}")
    print(f"  next_grammar_id starts at {next_grammar}_<slug>")
    print(f"  must_reuse_words populated with 5 lowest-occurrence words")
    print()
    print("Next: fill in theme/setting/notes and the new_word/new_grammar definition")
    print("      fields, then run `python3 pipeline/run.py --step 2`.")
    return 0


def scaffold_story(args) -> int:
    plan = json.loads(PLAN.read_text(encoding="utf-8")) if PLAN.exists() else {}
    sid = plan.get("story_id", 1)
    # If the user didn't override --sentences, default to the progression target.
    try:
        from progression import target_sentences as _tgt_sent
        if args.sentences is None:
            args.sentences = _tgt_sent(sid)
    except Exception:
        if args.sentences is None:
            args.sentences = 7

    title = {
        "jp": plan.get("title_jp", "<title>"),
        "en": plan.get("title_en", "<title>"),
        "tokens": [{"t": "<TODO>", "role": "content", "word_id": "<TODO>"}]
    }
    subtitle = {
        "jp": plan.get("subtitle_jp", "<subtitle>"),
        "en": plan.get("subtitle_en", "<subtitle>"),
        "tokens": [{"t": "<TODO>", "role": "content", "word_id": "<TODO>"}]
    }
    sentences = []
    for i in range(args.sentences):
        sentences.append({
            "idx": i,
            "gloss_en": "<English gloss — 0.8-3.0 x JP token count>",
            "tokens": [{"t": "<TODO>", "role": "content", "word_id": "<TODO>"}]
        })

    raw = {
        "story_id": sid,
        "title": title,
        "subtitle": subtitle,
        "new_words": plan.get("new_words", []),
        "new_grammar": plan.get("new_grammar", []),
        "all_words_used": [],   # precheck.py --fix will recompute
        "sentences": sentences
    }

    STORY_RAW.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✓ Wrote {STORY_RAW.relative_to(ROOT)}  (story_id={sid}, {args.sentences} sentence skeletons)")
    print()
    print("Schema reminders:")
    print("  - per-token: {t, role, word_id|grammar_id, [r], [is_new], [is_new_grammar], [inflection]}")
    print("  - role values: content | particle | aux | punct")
    print("  - first sentence-occurrence of each new_word needs is_new: true (NOT in title/subtitle)")
    print("  - ALL kanji content tokens need 'r' (kana reading)")
    print("  - polite/te/past forms need an 'inflection' block: {base, base_r, form, word_id}")
    print()
    print("After authoring, run:")
    print("  python3 pipeline/precheck.py --fix   # auto-fix idx, all_words_used, is_new")
    print("  python3 pipeline/run.py --step 3     # full validate")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_plan = sub.add_parser("plan", help="Scaffold pipeline/plan.json")
    p_plan.add_argument("--title-jp")
    p_plan.add_argument("--title-en")
    p_plan.add_argument("--subtitle-jp")
    p_plan.add_argument("--subtitle-en")
    p_plan.add_argument("--new-words", type=int, default=3)
    p_plan.add_argument("--new-grammar", type=int, default=1)
    p_plan.add_argument(
        "--new-word-surfaces",
        help="Comma-separated surfaces to auto-fill from JMdict (e.g. '猫,います'). "
             "Each surface populates one new_word_definition with kana/reading/pos/meanings.",
    )

    p_story = sub.add_parser("story", help="Scaffold pipeline/story_raw.json from current plan.json")
    p_story.add_argument("--sentences", type=int, default=None,
                         help="If omitted, uses the progression-curve target for the plan's story_id.")

    args = ap.parse_args()
    return scaffold_plan(args) if args.cmd == "plan" else scaffold_story(args)


if __name__ == "__main__":
    sys.exit(main())
