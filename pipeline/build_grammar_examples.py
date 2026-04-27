#!/usr/bin/env python3
"""
Monogatari — Grammar examples index builder.

Pre-computes a per-grammar-point example index so the reader can show
example sentences without crawling the entire corpus on first open. The
crawl path in the reader was O(N stories) network requests; this script
moves that work to build time so the reader does one fetch.

Output: data/grammar_examples.json

    {
      "version": 1,
      "generated_at": "...",
      "max_per_point": 5,
      "examples": {
        "G001": [
          {"story_id": 3, "sentence_idx": 2, "jp": "...", "gloss_en": "..."},
          ...
        ],
        ...
      }
    }

A grammar point is matched if any of its sentences contains a token whose
`grammar_id` OR `inflection.grammar_id` equals the point id.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sys
from pathlib import Path

MAX_PER_POINT = 5


def _scan(stories_dir: Path) -> dict[str, list[dict]]:
    examples: dict[str, list[dict]] = {}
    for path in sorted(
        stories_dir.glob("story_*.json"),
        key=lambda p: int(re.findall(r"(\d+)", p.stem)[0]),
    ):
        try:
            s = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  warning: skipped {path.name}: {e}", file=sys.stderr)
            continue
        story_id = s.get("story_id")
        for idx, sent in enumerate(s.get("sentences", [])):
            tokens = sent.get("tokens", [])
            gids: set[str] = set()
            for tok in tokens:
                gid = tok.get("grammar_id")
                if gid:
                    gids.add(gid)
                infl = tok.get("inflection") or {}
                if infl.get("grammar_id"):
                    gids.add(infl["grammar_id"])
            if not gids:
                continue
            jp = "".join(tok.get("t", "") for tok in tokens)
            gloss = sent.get("gloss_en", "")
            for gid in gids:
                bucket = examples.setdefault(gid, [])
                if len(bucket) >= MAX_PER_POINT:
                    continue
                bucket.append(
                    {
                        "story_id": story_id,
                        "sentence_idx": idx,
                        "jp": jp,
                        "gloss_en": gloss,
                    }
                )
    return examples


def build(stories_dir: Path) -> dict:
    return {
        "version": 1,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "max_per_point": MAX_PER_POINT,
        "examples": _scan(stories_dir),
    }


def main() -> None:
    stories_dir = Path("stories")
    if not stories_dir.exists():
        print(f"ERROR: {stories_dir} not found", file=sys.stderr)
        sys.exit(1)
    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build(stories_dir)
    out = out_dir / "grammar_examples.json"
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    n_points = len(payload["examples"])
    n_examples = sum(len(v) for v in payload["examples"].values())
    print(f"✓ Wrote {out}: {n_points} grammar points, {n_examples} examples")


if __name__ == "__main__":
    main()
