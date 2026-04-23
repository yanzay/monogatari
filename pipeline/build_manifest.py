#!/usr/bin/env python3
"""
Monogatari — Stories manifest builder.

Scans `stories/story_*.json` and writes `stories/index.json`, a small JSON
catalogue the reader uses instead of HEAD-probing for every story.

The manifest carries enough metadata for a "table of contents" view without
forcing the reader to download every story up front:

    {
      "version": 1,
      "generated_at": "2026-04-22T00:00:00Z",
      "stories": [
        {
          "story_id":     1,
          "path":         "stories/story_1.json",
          "title_jp":     "雨",
          "title_en":     "Rain",
          "n_sentences":  7,
          "n_content_tokens": 38,
          "n_new_words":  14,
          "n_new_grammar": 2,
          "has_audio":    true
        },
        ...
      ]
    }

The reader uses `n_sentences` + `n_content_tokens` to estimate reading
time, and `has_audio` to decide whether to show the play button.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sys
from pathlib import Path


def _scan_stories(stories_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(stories_dir.glob("story_*.json"),
                       key=lambda p: int(re.findall(r"(\d+)", p.stem)[0])):
        try:
            s = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  warning: skipped {path.name}: {e}", file=sys.stderr)
            continue
        sentences = s.get("sentences", [])
        n_content = sum(
            1 for sent in sentences for tok in sent.get("tokens", [])
            if tok.get("role") in ("content", "aux")
        )
        rows.append({
            "story_id":     s.get("story_id"),
            "path":         path.as_posix(),
            "title_jp":     (s.get("title") or {}).get("jp", ""),
            "title_en":     (s.get("title") or {}).get("en", ""),
            "n_sentences":  len(sentences),
            "n_content_tokens": n_content,
            "n_new_words":  len(s.get("new_words", [])),
            "n_new_grammar": len(s.get("new_grammar", [])),
            "has_audio":    bool(sentences and sentences[0].get("audio")),
        })
    return rows


def build(stories_dir: Path) -> dict:
    return {
        "version": 1,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "stories": _scan_stories(stories_dir),
    }


def main() -> None:
    stories_dir = Path("stories")
    if not stories_dir.exists():
        print(f"ERROR: {stories_dir} not found", file=sys.stderr)
        sys.exit(1)
    manifest = build(stories_dir)
    out = stories_dir / "index.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"✓ Wrote {out} with {len(manifest['stories'])} stories")


if __name__ == "__main__":
    main()
