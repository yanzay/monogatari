#!/usr/bin/env python3
"""Project derived vocab attributions to JSON for the reader app.

Phase B of the derive-on-read refactor (2026-05-01) makes corpus first/
last appearance + occurrence count the source of truth for vocab
attribution fields per word. The Svelte reader needs those values too
(WordPopup shows "First seen: Story N"; the vocab route filters by
first_story; reader analytics use occurrences) but cannot walk every
story JSON at page load. This script runs the derivation server-side
and writes a flat projection the reader can fetch with one HTTP request.

Output shape (matches `derived_state.VocabAttribution` per wid):

    {
      "version": 1,
      "generated_at": "2026-05-01T13:00:00+00:00",
      "n_words": 78,
      "attributions": {
        "W00001": {"first_story": "story_1",  "last_seen_story": "story_9",  "occurrences": 4},
        "W00002": {"first_story": "story_1",  "last_seen_story": "story_3",  "occurrences": 4},
        ...
      }
    }

Schema notes
------------
* `first_story` / `last_seen_story` are STRINGS (`"story_N"`),
  matching the historical vocab_state convention. Reader code already
  handles both `string` and `number` defensively (see
  `VocabIndexRow.first_story`); writing strings preserves the most
  idiomatic shape.
* `occurrences` is the TRUE corpus count — not the cached value that
  drifted out of sync in Phase A's pre-refactor state.

Writes BOTH `data/vocab_attributions.json` (for symmetry with
`vocab_state.json`) and `static/data/vocab_attributions.json` (the
file the reader fetches under `/data/vocab_attributions.json`). The
two paths are kept in sync so SvelteKit's static-asset pipeline picks
up the latest.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _paths import DATA, ROOT, write_json  # noqa: E402
from derived_state import derive_vocab_attributions  # noqa: E402


_DEST_DATA   = DATA / "vocab_attributions.json"
_DEST_STATIC = ROOT / "static" / "data" / "vocab_attributions.json"


def build_attributions_payload() -> dict:
    """Compute the on-disk shape of the manifest from the live corpus."""
    attrs = derive_vocab_attributions()
    payload = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_words": len(attrs),
        # Sort wids for deterministic on-disk output (helps git diffs).
        "attributions": {
            wid: {
                "first_story":     attrs[wid]["first_story"],
                "last_seen_story": attrs[wid]["last_seen_story"],
                "occurrences":     attrs[wid]["occurrences"],
            }
            for wid in sorted(attrs.keys())
        },
    }
    return payload


def write_attributions(payload: dict | None = None) -> tuple[Path, Path]:
    """Write the projection to both data/ and static/data/. Returns paths."""
    payload = payload or build_attributions_payload()
    _DEST_STATIC.parent.mkdir(parents=True, exist_ok=True)
    write_json(_DEST_DATA,   payload)
    write_json(_DEST_STATIC, payload)
    return _DEST_DATA, _DEST_STATIC


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the payload but don't write any files.")
    args = ap.parse_args(argv)

    payload = build_attributions_payload()

    if args.dry_run:
        import json as _json
        print(_json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    a, b = write_attributions(payload)
    print(f"Wrote {payload['n_words']} vocab attributions to:")
    print(f"  {a}")
    print(f"  {b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
