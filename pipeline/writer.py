#!/usr/bin/env python3
"""
Monogatari — Stage 2: Story Writer (Rovo Dev mode)

Generates the writer prompt from plan.json and writes it to a file.
Rovo Dev reads the prompt and produces story_raw.json.

Usage:
    # Step 1: generate the writer prompt
    python3 pipeline/writer.py \
        [--plan pipeline/plan.json] \
        [--vocab data/vocab_state.json] \
        [--grammar data/grammar_state.json] \
        [--rules pipeline/authoring_rules.md] \
        [--prompt-out pipeline/writer_prompt.md]

    # Step 2: Rovo Dev reads pipeline/writer_prompt.md
    #         and writes pipeline/story_raw.json

    # Step 3: validate
    python3 pipeline/validate.py pipeline/story_raw.json --plan pipeline/plan.json
"""

import argparse
import json
import sys
from pathlib import Path


# ── Prompt builder ────────────────────────────────────────────────────────────

WRITER_PROMPT_TEMPLATE = """\
# Monogatari — Story Writer Task

You are writing story **{story_id}** for the Monogatari Japanese graded-reader.
Read the authoring rules and plan below, then produce the story JSON.
Output **only** the JSON object — no prose, no markdown fences.

---

## Authoring Rules

{authoring_rules}

---

## Plan

```json
{plan_json}
```

---

## Allowed vocabulary (ALL words you may use — no others)

{allowed_words}

---

## Allowed grammar (ALL grammar_ids you may use — no others)

{allowed_grammar}

---

## New word definitions (introduce these in the story)

{new_word_defs}

---

## Output schema

Produce a `story_{story_id}.json` object with this structure:

```json
{{
  "story_id": {story_id},
  "title": {{
    "jp": "<kanji/kana title>",
    "en": "<English title>",
    "tokens": [
      {{"t": "<kanji>", "r": "<kana>", "word_id": "<id>", "role": "content"}}
    ]
  }},
  "subtitle": {{
    "jp": "<subtitle>",
    "en": "<English subtitle>",
    "tokens": [ ... ]
  }},
  "plan_ref": "plan.json",
  "new_words": {new_words_json},
  "new_grammar": {new_grammar_json},
  "all_words_used": ["<every word_id used, in order of first appearance>"],
  "sentences": [
    {{
      "idx": 0,
      "tokens": [
        {{"t": "<kanji>", "r": "<kana reading>", "word_id": "<id>", "role": "content", "is_new": true}},
        {{"t": "<particle>", "grammar_id": "<gid>", "role": "particle"}},
        {{"t": "<inflected>", "r": "<kana>", "word_id": "<id>", "role": "content",
          "inflection": {{"base": "<dict-kanji>", "base_r": "<dict-kana>", "form": "te_form", "grammar_id": "<gid>"}}}},
        {{"t": "。", "role": "punct"}}
      ],
      "gloss_en": "<natural English>",
      "audio": null
    }}
  ],
  "word_audio": {{}},
  "checksum": null
}}
```

### Rules reminder
- Every `role: content` token needs `word_id`
- Every `role: particle` or `role: aux` token needs `grammar_id`
- Every token whose `t` contains kanji needs `r` (full kana reading)
- Inflected forms need an `inflection` block
- `is_new: true` on first occurrence of each new word
- `is_new_grammar: true` on first occurrence of each new grammar point
- 5–8 sentences
- Each new word appears at least twice
- New grammar appears at least 3 times (if introduced)

If you cannot satisfy the constraints, output:
```json
{{"error": "cannot_generate", "reason": "...", "missing_vocab": [], "missing_grammar": []}}
```
"""


def build_allowed_words(vocab: dict, plan: dict) -> str:
    words    = vocab.get("words", {})
    new_defs = plan.get("new_word_definitions", {})
    lines    = []
    for wid, w in sorted(words.items()):
        occ = w.get("occurrences", 0)
        lines.append(
            f"- `{wid}`: **{w['surface']}** ({w['kana']}) "
            f"[{w.get('pos','')}] — {', '.join(w['meanings'][:2])} "
            f"[occ:{occ}]"
        )
    for wid, w in new_defs.items():
        if wid not in words:
            lines.append(
                f"- `{wid}`: **{w.get('surface',wid)}** ({w.get('kana','')}) "
                f"[{w.get('pos','')}] — {', '.join(w.get('meanings',[]))} **[NEW]**"
            )
    return "\n".join(lines)


def build_allowed_grammar(grammar: dict, plan: dict) -> str:
    points = grammar.get("points", {})
    new_g  = plan.get("new_grammar", [])
    lines  = []
    for gid, gp in sorted(points.items()):
        lines.append(f"- `{gid}`: {gp['title']} — {gp['short']}")
    for gid in new_g:
        if gid not in points:
            lines.append(f"- `{gid}`: **[NEW grammar point — define in story]**")
    return "\n".join(lines)


def build_new_word_defs(plan: dict) -> str:
    defs = plan.get("new_word_definitions", {})
    if not defs:
        return "_No definitions provided — infer from new_words list._"
    lines = []
    for wid, w in defs.items():
        vc = f" · {w['verb_class']}" if w.get("verb_class") else ""
        ac = f" · {w['adj_class']}-adj" if w.get("adj_class") else ""
        lines.append(
            f"- `{wid}`: **{w.get('surface','')}** ({w.get('kana','')}) "
            f"[{w.get('pos','')}{vc}{ac}] — {', '.join(w.get('meanings',[]))}"
        )
    return "\n".join(lines)


def build_prompt(plan: dict, vocab: dict, grammar: dict, rules: str) -> str:
    story_id = plan.get("story_id", "?")
    return WRITER_PROMPT_TEMPLATE.format(
        story_id=story_id,
        authoring_rules=rules,
        plan_json=json.dumps(plan, ensure_ascii=False, indent=2),
        allowed_words=build_allowed_words(vocab, plan),
        allowed_grammar=build_allowed_grammar(grammar, plan),
        new_word_defs=build_new_word_defs(plan),
        new_words_json=json.dumps(plan.get("new_words", []), ensure_ascii=False),
        new_grammar_json=json.dumps(plan.get("new_grammar", []), ensure_ascii=False),
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Monogatari Story Writer")
    parser.add_argument("--plan",       default="pipeline/plan.json")
    parser.add_argument("--vocab",      default="data/vocab_state.json")
    parser.add_argument("--grammar",    default="data/grammar_state.json")
    parser.add_argument("--rules",      default="pipeline/authoring_rules.md")
    parser.add_argument("--prompt-out", default="pipeline/writer_prompt.md")
    args = parser.parse_args()

    plan    = load_json(args.plan)
    vocab   = load_json(args.vocab)
    grammar = load_json(args.grammar)
    rules   = load_text(args.rules)

    if "error" in plan:
        print(f"ERROR: plan.json contains an error: {plan['error']}", file=sys.stderr)
        sys.exit(1)

    prompt   = build_prompt(plan, vocab, grammar, rules)
    out_path = Path(args.prompt_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(prompt, encoding="utf-8")

    story_id = plan.get("story_id", "?")
    print(f"✓ Writer prompt written to {out_path}")
    print(f"\nNext steps:")
    print(f"  1. Ask Rovo Dev: 'Execute the writer prompt in {out_path} and write pipeline/story_raw.json'")
    print(f"  2. python3 pipeline/validate.py pipeline/story_raw.json --plan {args.plan}")
    print(f"  3. (if valid) python3 pipeline/state_updater.py pipeline/story_raw.json --plan {args.plan}")


if __name__ == "__main__":
    main()
