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


def scaffold_plan(args) -> int:
    vocab, grammar, next_story, next_word, next_grammar = load_state()
    new_words = []
    new_word_defs = {}
    nw_int = int(next_word[1:])
    for i in range(args.new_words):
        wid = f"W{nw_int + i:05d}"
        new_words.append(wid)
        new_word_defs[wid] = {
            "id": wid,
            "surface": "<kanji or kana>",
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
        "target_word_count": 24,
        "max_sentences": 7,
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

    p_story = sub.add_parser("story", help="Scaffold pipeline/story_raw.json from current plan.json")
    p_story.add_argument("--sentences", type=int, default=6)

    args = ap.parse_args()
    return scaffold_plan(args) if args.cmd == "plan" else scaffold_story(args)


if __name__ == "__main__":
    sys.exit(main())
