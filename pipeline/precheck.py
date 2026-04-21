#!/usr/bin/env python3
"""
Fast pre-flight check for pipeline/story_raw.json.

Catches the common authoring mistakes BEFORE running the full validator,
and offers --fix to repair the cheap ones automatically:

  * missing top-level fields:  story_id, new_words, new_grammar
  * missing per-sentence idx
  * stale all_words_used (wrong order, missing ids, extra ids)
  * is_new placement (must be on first sentence-token, not on title token)
  * gloss_en length out of [0.8, 3.0] x JP-token-count
  * stub words (W##### referenced but not in vocab + not in new_words)
  * stub grammar (G##### referenced but not in grammar + not in new_grammar)
  * verb form note: 見ます etc. need an inflection block (warning only)

Usage:
    python3 pipeline/precheck.py            # report only
    python3 pipeline/precheck.py --fix      # auto-fix the cheap ones, keep a backup
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORY_RAW = ROOT / "pipeline" / "story_raw.json"
VOCAB = ROOT / "data" / "vocab_state.json"
GRAMMAR = ROOT / "data" / "grammar_state.json"

GLOSS_MIN_RATIO = 0.8
GLOSS_MAX_RATIO = 3.0


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def first_seen_word_order(story: dict) -> list[str]:
    """Compute the canonical all_words_used: every word_id in first-seen order
    across title -> subtitle -> sentences (in order)."""
    seen: list[str] = []
    seen_set: set[str] = set()

    def visit(tokens: list[dict]) -> None:
        for tok in tokens:
            wid = tok.get("word_id")
            if wid and wid not in seen_set:
                seen.append(wid)
                seen_set.add(wid)

    if title := story.get("title"):
        visit(title.get("tokens", []))
    if subtitle := story.get("subtitle"):
        visit(subtitle.get("tokens", []))
    for sent in story.get("sentences", []):
        visit(sent.get("tokens", []))
    return seen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fix", action="store_true", help="Auto-fix the cheap problems and write back")
    ap.add_argument("--story", type=Path, default=STORY_RAW, help="Path to story_raw.json (default: pipeline/story_raw.json)")
    args = ap.parse_args()

    if not args.story.exists():
        print(f"✗ {args.story} not found.")
        return 1

    story = load_json(args.story)
    vocab = load_json(VOCAB)
    grammar = load_json(GRAMMAR)
    known_words = set(vocab["words"].keys())
    known_grammar = set(grammar["points"].keys())

    errors: list[str] = []
    warnings: list[str] = []
    fixes_applied: list[str] = []

    # ── 1. top-level required fields ─────────────────────────────────────────
    for field in ("story_id", "title", "subtitle", "sentences"):
        if field not in story:
            errors.append(f"missing top-level field '{field}'")

    if "new_words" not in story:
        if args.fix:
            story["new_words"] = []
            fixes_applied.append("added empty new_words array")
        else:
            errors.append("missing top-level 'new_words' (use [] if none)")

    if "new_grammar" not in story:
        if args.fix:
            story["new_grammar"] = []
            fixes_applied.append("added empty new_grammar array")
        else:
            errors.append("missing top-level 'new_grammar' (use [] if none)")

    declared_new_words = set(story.get("new_words") or [])
    declared_new_grammar = set(story.get("new_grammar") or [])

    # ── 2. per-sentence idx ──────────────────────────────────────────────────
    for i, sent in enumerate(story.get("sentences", [])):
        if "idx" not in sent:
            if args.fix:
                sent["idx"] = i
                fixes_applied.append(f"sentence[{i}]: added idx")
            else:
                errors.append(f"sentence[{i}] missing 'idx' field")

    # ── 3. all_words_used canonical order ────────────────────────────────────
    canonical = first_seen_word_order(story)
    declared = list(story.get("all_words_used") or [])
    if canonical != declared:
        if args.fix:
            story["all_words_used"] = canonical
            fixes_applied.append(f"all_words_used recomputed (was {len(declared)} ids, now {len(canonical)})")
        else:
            extra = set(declared) - set(canonical)
            missing = set(canonical) - set(declared)
            details = []
            if extra:
                details.append(f"extra={sorted(extra)}")
            if missing:
                details.append(f"missing={sorted(missing)}")
            if not extra and not missing:
                details.append("wrong order — should be first-seen order across title→subtitle→sentences")
            errors.append("all_words_used is stale: " + ", ".join(details))

    # ── 4. is_new placement (must be on first sentence-token, not title) ─────
    title_toks = (story.get("title") or {}).get("tokens", [])
    subtitle_toks = (story.get("subtitle") or {}).get("tokens", [])
    for tok in title_toks + subtitle_toks:
        if tok.get("is_new") and tok.get("word_id") in declared_new_words:
            if args.fix:
                del tok["is_new"]
                fixes_applied.append(f"removed is_new from title/subtitle token '{tok.get('t')}' (must live on first sentence-token)")
            else:
                errors.append(f"title/subtitle token '{tok.get('t')}' has is_new=true — must live on the FIRST SENTENCE-token, not in title/subtitle")

    # find first sentence-occurrence and ensure is_new is set there exactly once
    for wid in declared_new_words:
        first_sentence_tok = None
        for sent in story.get("sentences", []):
            for tok in sent["tokens"]:
                if tok.get("word_id") == wid:
                    first_sentence_tok = tok
                    break
            if first_sentence_tok is not None:
                break
        if first_sentence_tok is None:
            errors.append(f"new_word '{wid}' declared but never used in any sentence")
            continue
        if not first_sentence_tok.get("is_new"):
            if args.fix:
                first_sentence_tok["is_new"] = True
                fixes_applied.append(f"new_word '{wid}': added is_new on first sentence-token '{first_sentence_tok.get('t')}'")
            else:
                errors.append(f"new_word '{wid}': first sentence-token '{first_sentence_tok.get('t')}' missing is_new=true")

    # ── 5. gloss length ratio ────────────────────────────────────────────────
    for sent in story.get("sentences", []):
        gloss = sent.get("gloss_en", "")
        jp_tokens = [t for t in sent["tokens"] if t.get("role") != "punct"]
        jp_count = len(jp_tokens)
        en_count = len(gloss.split())
        if jp_count > 0:
            ratio = en_count / jp_count
            if not (GLOSS_MIN_RATIO <= ratio <= GLOSS_MAX_RATIO):
                tip = "expand the gloss" if ratio < GLOSS_MIN_RATIO else "tighten the gloss"
                errors.append(
                    f"sentence[{sent.get('idx', '?')}] gloss ratio {ratio:.2f} outside [{GLOSS_MIN_RATIO}, {GLOSS_MAX_RATIO}] "
                    f"(EN words {en_count} / JP tokens {jp_count}) — {tip}: '{gloss}'"
                )

    # ── 6. id sanity (vocab + grammar) ───────────────────────────────────────
    for sent in story.get("sentences", []):
        for j, tok in enumerate(sent["tokens"]):
            wid = tok.get("word_id")
            if wid and wid not in known_words and wid not in declared_new_words:
                errors.append(f"sentence[{sent.get('idx', '?')}] token[{j}] '{tok.get('t')}' references unknown word_id '{wid}' (not in vocab and not in new_words)")
            for gid in (tok.get("grammar_id"), (tok.get("inflection") or {}).get("grammar_id")):
                if gid and gid not in known_grammar and gid not in declared_new_grammar:
                    errors.append(f"sentence[{sent.get('idx', '?')}] token[{j}] '{tok.get('t')}' references unknown grammar_id '{gid}'")

    # ── 7. inflection-needed warning for masu/te/past content tokens ─────────
    for sent in story.get("sentences", []):
        for j, tok in enumerate(sent["tokens"]):
            wid = tok.get("word_id")
            if not wid:
                continue
            t = tok.get("t", "")
            inf = tok.get("inflection")
            word = vocab["words"].get(wid)
            if word and word.get("pos") == "verb":
                # heuristic: if surface != dictionary kana AND no inflection block, warn
                if t.endswith("ます") and not inf:
                    warnings.append(f"sentence[{sent.get('idx', '?')}] token[{j}] '{t}' looks like polite_nonpast but has no 'inflection' block")
                if (t.endswith("て") or t.endswith("で")) and not inf:
                    warnings.append(f"sentence[{sent.get('idx', '?')}] token[{j}] '{t}' looks like te-form but has no 'inflection' block")

    # ── output + write back ──────────────────────────────────────────────────
    if args.fix and fixes_applied:
        backup = args.story.with_suffix(".json.bak")
        shutil.copy2(args.story, backup)
        args.story.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"── auto-fixed {len(fixes_applied)} problem(s) (backup at {backup.name}) ──")
        for f in fixes_applied:
            print(f"  ✓ {f}")
        print()

    if errors:
        print(f"── {len(errors)} ERROR(S) ──")
        for e in errors:
            print(f"  ✗ {e}")
    if warnings:
        print(f"\n── {len(warnings)} warning(s) ──")
        for w in warnings:
            print(f"  ! {w}")

    if not errors and not warnings:
        if args.fix:
            print("✓ Pre-check clean (after auto-fix). Run `python3 pipeline/run.py --step 3` next.")
        else:
            print("✓ Pre-check clean. Run `python3 pipeline/run.py --step 3` next.")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
