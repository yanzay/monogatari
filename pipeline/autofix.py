"""
autofix.py — repair common authoring slips in pipeline/story_raw.json.

Targets the gotchas inventoried in docs/authoring.md ("Authoring gotchas").
Idempotent and conservative: only changes things that are definitely wrong;
never touches surface text or sentence structure.

Fixes:
  1. Wrong word_id  → resolve from surface against vocab_state.json
                      (warns if multiple homographs match — leaves it alone).
  2. Missing word_id on a content token whose surface IS in vocab.
  3. is_new placement → ensure exactly the first sentence-level content
     occurrence of each new_word has is_new: true (drop it from title/subtitle
     and from later occurrences).
  4. all_words_used → recompute in first-seen order across title → subtitle
     → sentences in document order.
  5. Sentence idx → set sequentially if missing or out of order.
  6. Tag past-tense verb tokens (inflection.form ∈ {polite_past, plain_past})
     with grammar_id G013_mashita_past if grammar G013 exists in state.
  7. Pure-grammar tokens that wrongly carry a word_id (です, だ, と, も…) →
     drop the word_id, keep grammar_id.

Run:
    python3 pipeline/autofix.py            # writes back to pipeline/story_raw.json
    python3 pipeline/autofix.py --dry-run  # show diff only
    python3 pipeline/autofix.py --story stories/story_12.json
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT  = Path(__file__).resolve().parent.parent
VOCAB = ROOT / "data" / "vocab_state.json"
GRAM  = ROOT / "data" / "grammar_state.json"

# Surfaces that should NEVER carry a word_id — they are grammar/aux/particles.
GRAMMAR_SURFACES = {
    "です", "だ", "でした", "じゃない", "ではない",
    "は", "が", "を", "に", "で", "へ", "と", "や", "も", "の",
    "か", "ね", "よ", "から", "まで", "より", "など",
    "そして", "でも", "けど", "しかし",
    "ます", "ました", "ません",
    "、", "。", "？", "！", "…",
}

def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))

def save(p: Path, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")

def build_surface_index(words_dict: dict) -> dict[str, list[str]]:
    """surface → [wid, ...] (length > 1 for homographs)."""
    idx: dict[str, list[str]] = {}
    for wid, w in words_dict.items():
        s = w.get("surface", "")
        if s:
            idx.setdefault(s, []).append(wid)
    return idx

def collect_token_lists(story):
    """Yield (label, list_of_tokens) for every section that has tokens."""
    if "title" in story and "tokens" in story["title"]:
        yield "title", story["title"]["tokens"]
    if "subtitle" in story and "tokens" in story["subtitle"]:
        yield "subtitle", story["subtitle"]["tokens"]
    for i, snt in enumerate(story.get("sentences", [])):
        yield f"sentence {i}", snt.get("tokens", [])

def fix_story(story: dict, words_dict: dict, grammar_points: dict,
              changes: list[str]) -> dict:
    surface_idx = build_surface_index(words_dict)
    new_words = set(story.get("new_words", []))

    # ── Fix 1+2+7: word_id repair ────────────────────────────────────────
    for label, tokens in collect_token_lists(story):
        for j, tok in enumerate(tokens):
            surface = tok.get("t", "")
            wid     = tok.get("word_id")
            role    = tok.get("role", "")

            # Fix 7: pure-grammar surface should not carry a word_id
            if surface in GRAMMAR_SURFACES and wid:
                changes.append(f"{label}[{j}] '{surface}': drop wrong word_id={wid} (grammar surface)")
                tok.pop("word_id", None)
                if role == "content":
                    tok["role"] = "particle" if surface in {"は","が","を","に","で","へ","と","や","も","の","か","ね","よ","から","まで","より","など"} else "aux"
                continue

            # Fix 1: content token surface present in vocab — verify wid matches
            if role == "content" and surface and surface not in GRAMMAR_SURFACES:
                hits = surface_idx.get(surface, [])
                if len(hits) == 1:
                    correct = hits[0]
                    if wid != correct:
                        if wid is None:
                            changes.append(f"{label}[{j}] '{surface}': set word_id={correct}")
                        else:
                            changes.append(f"{label}[{j}] '{surface}': fix word_id {wid} → {correct}")
                        tok["word_id"] = correct
                elif len(hits) > 1 and wid not in hits:
                    changes.append(f"{label}[{j}] '{surface}': WARN homograph {hits} — current {wid} not among them, leaving as-is")

    # ── Fix 6: tag past-form verbs with G013 ────────────────────────────
    has_g013 = "G013_mashita_past" in grammar_points
    if has_g013:
        for label, tokens in collect_token_lists(story):
            for j, tok in enumerate(tokens):
                inf = tok.get("inflection") or {}
                if inf.get("form") in ("polite_past", "plain_past"):
                    if tok.get("grammar_id") != "G013_mashita_past":
                        # Don't overwrite an existing different grammar tag silently
                        if not tok.get("grammar_id"):
                            changes.append(f"{label}[{j}] '{tok.get('t','')}': tag past form with G013_mashita_past")
                            tok["grammar_id"] = "G013_mashita_past"

    # ── Fix 5: sentence idx ─────────────────────────────────────────────
    for i, snt in enumerate(story.get("sentences", [])):
        if snt.get("idx") != i:
            changes.append(f"sentence {i}: set idx={i}")
            snt["idx"] = i

    # ── Fix 3: is_new on first sentence occurrence only ─────────────────
    # Strip is_new from title/subtitle
    for sec in ("title", "subtitle"):
        for j, tok in enumerate((story.get(sec) or {}).get("tokens", [])):
            if tok.pop("is_new", None):
                changes.append(f"{sec}[{j}]: drop is_new (only sentence-level allowed)")
    # Re-place is_new on first sentence occurrence per new_word
    seen_new: set[str] = set()
    for i, snt in enumerate(story.get("sentences", [])):
        for j, tok in enumerate(snt.get("tokens", [])):
            wid = tok.get("word_id")
            if wid in new_words and wid not in seen_new:
                if not tok.get("is_new"):
                    changes.append(f"sentence {i} token {j} '{tok.get('t','')}': set is_new=true (first occurrence of {wid})")
                    tok["is_new"] = True
                seen_new.add(wid)
            elif wid in new_words:
                if tok.pop("is_new", None):
                    changes.append(f"sentence {i} token {j} '{tok.get('t','')}': drop is_new (not first occurrence)")

    # ── Fix 4: all_words_used in first-seen order ───────────────────────
    order: list[str] = []
    for _, tokens in collect_token_lists(story):
        for tok in tokens:
            wid = tok.get("word_id")
            if wid and wid not in order:
                order.append(wid)
    if story.get("all_words_used") != order:
        changes.append(f"all_words_used: recomputed ({len(order)} words in first-seen order)")
        story["all_words_used"] = order

    return story

def main() -> int:
    ap = argparse.ArgumentParser(description="Auto-repair common authoring slips in story_raw.json.")
    ap.add_argument("--story", default=str(ROOT / "pipeline" / "story_raw.json"),
                    help="Path to story_raw.json (default: pipeline/story_raw.json)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would change without writing.")
    args = ap.parse_args()

    story_path = Path(args.story)
    if not story_path.exists():
        print(f"ERROR: {story_path} not found", file=sys.stderr); return 1

    story          = load(story_path)
    vocab          = load(VOCAB)
    grammar        = load(GRAM)
    words_dict     = vocab.get("words", {})
    grammar_points = grammar.get("points", {})

    changes: list[str] = []
    story = fix_story(story, words_dict, grammar_points, changes)

    if not changes:
        print("✓ No fixes needed.")
        return 0

    print(f"── {len(changes)} fix(es) ──")
    for c in changes:
        print(f"  • {c}")

    if args.dry_run:
        print("\n(dry-run; no file written)")
    else:
        save(story_path, story)
        print(f"\n✓ Wrote {story_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
