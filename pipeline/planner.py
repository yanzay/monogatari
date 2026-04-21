#!/usr/bin/env python3
"""
Monogatari — Stage 1: Story Planner (Rovo Dev mode)

Generates the planner prompt and writes it to a file for Rovo Dev to execute.
Rovo Dev reads the prompt, produces plan.json, and saves it.

Usage:
    # Step 1: generate the prompt
    python3 pipeline/planner.py \
        --n-new-words 3 \
        [--theme "evening walk"] \
        [--vocab data/vocab_state.json] \
        [--grammar data/grammar_state.json] \
        [--prompt-out pipeline/planner_prompt.md]

    # Step 2: Rovo Dev reads pipeline/planner_prompt.md and writes pipeline/plan.json

    # Step 3: validate the plan
    python3 pipeline/planner.py --validate pipeline/plan.json
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone


# ── Prompt builder ────────────────────────────────────────────────────────────

PLANNER_PROMPT_TEMPLATE = """\
# Monogatari — Story Planner Task

You are producing `plan.json` for story {story_id} of the Monogatari graded-reader.
Read everything below carefully. Output **only** the JSON object — no prose.

---

## Learner's current vocabulary ({n_words} words)

{vocab_summary}

## Learner's current grammar ({n_grammar} points)

{grammar_summary}

## Words most in need of reinforcement (occurrences < 5)

{weak_words}

---

## Difficulty policy for story {story_id}

- Introduce exactly **{n_new_words}** new words.
- Optionally introduce at most **{n_new_grammar}** new grammar point(s). Zero is fine.
- Story length: 5–8 sentences, 35–65 content tokens total.
- At least 60% of content tokens must be previously-seen words with occurrences < 5.
- New grammar prerequisites must all already exist in grammar_state.
- New words must be i+1: high-frequency, concrete, combinable with existing vocab.
- Avoid: violence, romance beyond friendship, politics, religion, graphic content.
{theme_hint}

## Next available word ID

The next sequential word ID is: **{next_word_id}**
(assign new IDs from here upward: {next_word_id}, {next_word_id2}, {next_word_id3}, …)

---

## Output schema

Produce this exact JSON object:

```json
{{
  "story_id": {story_id},
  "target_word_count": <integer 35-65>,
  "max_sentences": 8,
  "new_words": ["<id1>", "<id2>", "<id3>"],
  "new_grammar": ["<gid>" ],
  "theme": "<2-5 word theme>",
  "setting": "<one sentence describing the scene>",
  "constraints": {{
    "must_reuse_words": ["<up to 5 word_ids most needing reinforcement>"],
    "forbidden_words": [],
    "avoid_topics": ["violence", "romance", "politics"]
  }},
  "new_word_definitions": {{
    "<word_id>": {{
      "surface": "<kanji form or kana if no kanji>",
      "kana": "<hiragana>",
      "reading": "<romaji>",
      "pos": "<noun|verb|adjective|adverb|pronoun>",
      "verb_class": "<ichidan|godan|null>",
      "adj_class": "<i|na|null>",
      "meanings": ["<primary English meaning>"],
      "grammar_tags": []
    }}
  }},
  "new_grammar_definitions": {{
    "<grammar_id>": {{
      "title": "<short Japanese form + English label, e.g. 'も — also / too'>",
      "short": "<one-line description shown in tooltips>",
      "long":  "<full explanation: usage, examples, common pitfalls>",
      "genki_ref": "<e.g. L2 or null>",
      "prerequisites": ["<existing grammar_id>", ...]
    }}
  }},
  "rationale": "<one paragraph explaining word choices>",
  "seed": <random integer>
}}
```

> Every entry in `new_grammar` MUST have a corresponding entry in
> `new_grammar_definitions`. Ship-time state validation will reject placeholders.
"""


def build_vocab_summary(vocab: dict) -> str:
    words = vocab.get("words", {})
    lines = []
    for wid, w in sorted(words.items()):
        lines.append(
            f"- `{wid}`: **{w['surface']}** ({w['kana']}) — {', '.join(w['meanings'][:2])}"
            f" [occ:{w.get('occurrences',0)}, story:{w.get('first_story','?')}]"
        )
    return "\n".join(lines)


def build_grammar_summary(grammar: dict) -> str:
    points = grammar.get("points", {})
    lines = []
    for gid, gp in sorted(points.items()):
        lines.append(f"- `{gid}`: {gp['title']} — {gp['short']}")
    return "\n".join(lines)


def build_weak_words(vocab: dict, n: int = 8) -> str:
    words = vocab.get("words", {})
    sorted_weak = sorted(
        [(w.get("occurrences", 0), wid, w["surface"], w["kana"], w["meanings"][0])
         for wid, w in words.items()],
        key=lambda x: x[0]
    )[:n]
    return "\n".join(
        f"- `{wid}`: **{surf}** ({kana}) — {meaning} [occ:{occ}]"
        for occ, wid, surf, kana, meaning in sorted_weak
    )


def next_word_id(vocab: dict) -> tuple[str, str, str]:
    existing = [int(wid[1:]) for wid in vocab.get("words", {}) if wid.startswith("W")]
    n = (max(existing) + 1) if existing else 1
    return (f"W{n:05d}", f"W{n+1:05d}", f"W{n+2:05d}")


def build_prompt(vocab: dict, grammar: dict, story_id: int,
                 n_new_words: int, n_new_grammar: int, theme: str | None) -> str:
    nw1, nw2, nw3 = next_word_id(vocab)
    return PLANNER_PROMPT_TEMPLATE.format(
        story_id=story_id,
        n_words=len(vocab.get("words", {})),
        n_grammar=len(grammar.get("points", {})),
        vocab_summary=build_vocab_summary(vocab),
        grammar_summary=build_grammar_summary(grammar),
        weak_words=build_weak_words(vocab),
        n_new_words=n_new_words,
        n_new_grammar=n_new_grammar,
        theme_hint=f'- Theme hint: "{theme}"' if theme else "",
        next_word_id=nw1,
        next_word_id2=nw2,
        next_word_id3=nw3,
    )


# ── Plan validator ────────────────────────────────────────────────────────────

def validate_plan(plan: dict, vocab: dict, grammar: dict) -> list[str]:
    errors = []
    known_words   = set(vocab.get("words", {}).keys())
    known_grammar = set(grammar.get("points", {}).keys())

    for field in ("story_id", "new_words", "new_grammar", "theme", "setting",
                  "constraints", "new_word_definitions"):
        if field not in plan:
            errors.append(f"Missing field: '{field}'")

    # new_words must NOT already be in vocab
    for wid in plan.get("new_words", []):
        if wid in known_words:
            errors.append(f"new_word '{wid}' already exists in vocab_state")

    # Every new_word must have a definition in new_word_definitions
    word_defs = plan.get("new_word_definitions", {})
    for wid in plan.get("new_words", []):
        if wid not in word_defs:
            errors.append(f"new_word '{wid}' missing entry in 'new_word_definitions'")
        else:
            d = word_defs[wid]
            for key in ("surface", "kana", "reading", "pos", "meanings"):
                if not d.get(key):
                    errors.append(f"new_word '{wid}' definition missing required field '{key}'")

    # Every new_grammar must have a full definition in new_grammar_definitions
    grammar_defs = plan.get("new_grammar_definitions", {})
    for gid in plan.get("new_grammar", []):
        if gid in known_grammar:
            errors.append(f"new_grammar '{gid}' already exists in grammar_state")
        if gid not in grammar_defs:
            errors.append(
                f"new_grammar '{gid}' missing entry in 'new_grammar_definitions' "
                "(title/short/long/prerequisites must all be provided)"
            )
            continue
        gd = grammar_defs[gid]
        for key in ("title", "short", "long"):
            val = gd.get(key)
            if not val or not str(val).strip() or str(val).strip() == gid:
                errors.append(f"new_grammar '{gid}' definition missing/placeholder '{key}'")
        for p in gd.get("prerequisites", []) or []:
            if p not in known_grammar:
                errors.append(f"Grammar prerequisite '{p}' for '{gid}' not in grammar_state")

    # must_reuse_words must exist in vocab
    for wid in plan.get("constraints", {}).get("must_reuse_words", []):
        if wid not in known_words:
            errors.append(f"must_reuse_word '{wid}' not in vocab_state")

    return errors


# ── CLI ───────────────────────────────────────────────────────────────────────

def load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Monogatari Story Planner")
    parser.add_argument("--n-new-words",   type=int, default=3)
    parser.add_argument("--n-new-grammar", type=int, default=1)
    parser.add_argument("--theme",         default=None)
    parser.add_argument("--vocab",         default="data/vocab_state.json")
    parser.add_argument("--grammar",       default="data/grammar_state.json")
    parser.add_argument("--prompt-out",    default="pipeline/planner_prompt.md")
    parser.add_argument("--validate",      metavar="PLAN_JSON",
                        help="Validate an existing plan.json")
    args = parser.parse_args()

    vocab   = load_json(args.vocab)
    grammar = load_json(args.grammar)

    # Validate mode
    if args.validate:
        plan   = load_json(args.validate)
        errors = validate_plan(plan, vocab, grammar)
        if errors:
            print(f"✗ Plan invalid ({len(errors)} error(s)):")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        else:
            print("✓ Plan valid")
            print(f"  story_id:   {plan.get('story_id')}")
            print(f"  new_words:  {plan.get('new_words')}")
            print(f"  theme:      {plan.get('theme')}")
        return

    story_id = vocab.get("last_story_id", 0) + 1
    prompt   = build_prompt(vocab, grammar, story_id,
                            args.n_new_words, args.n_new_grammar, args.theme)

    out_path = Path(args.prompt_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(prompt, encoding="utf-8")

    print(f"✓ Planner prompt written to {out_path}")
    print(f"\nNext steps:")
    print(f"  1. Ask Rovo Dev: 'Execute the planner prompt in {out_path} and write pipeline/plan.json'")
    print(f"  2. Review pipeline/plan.json")
    print(f"  3. python3 pipeline/planner.py --validate pipeline/plan.json")
    print(f"  4. python3 pipeline/writer.py (generates writer prompt)")


if __name__ == "__main__":
    main()
