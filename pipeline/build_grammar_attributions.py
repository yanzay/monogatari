#!/usr/bin/env python3
"""Project derived grammar attributions to JSON for the reader app.

Phase A of the derive-on-read refactor (2026-05-01) makes corpus first/
last appearance the source of truth for `intro_in_story` and
`last_seen_story` per grammar point. The Svelte reader needs those
values too (the grammar route filters to "introduced in some shipped
story"; the known-filters utility uses `intro_in_story` to decide
"seen") but cannot walk every story JSON at page load. This script
runs the derivation server-side and writes a flat projection the
reader can fetch with one HTTP request.

Output shape (matches `derived_state.GrammarAttribution` per gid):

    {
      "version": 1,
      "generated_at": "2026-05-01T12:00:00+00:00",
      "n_introduced": 31,
      "attributions": {
        "N5_wa_topic":  {"intro_in_story": 1,  "last_seen_story": 10},
        "N5_da":        {"intro_in_story": 5,  "last_seen_story": 9},
        ...
      }
    }

Writes BOTH `data/grammar_attributions.json` (for symmetry with
`grammar_state.json` / `grammar_catalog.json`) and
`static/data/grammar_attributions.json` (the file the reader fetches
under `/data/grammar_attributions.json`). The two paths are kept in
sync so SvelteKit's static-asset pipeline picks up the latest.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _paths import DATA, ROOT, write_json  # noqa: E402
from derived_state import derive_grammar_attributions  # noqa: E402


_DEST_DATA   = DATA / "grammar_attributions.json"
_DEST_STATIC = ROOT / "static" / "data" / "grammar_attributions.json"


def build_attributions_payload() -> dict:
    """Compute the on-disk shape of the manifest from the live corpus."""
    attrs = derive_grammar_attributions()
    payload = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_introduced": len(attrs),
        # Sort gids for deterministic on-disk output (helps git diffs).
        "attributions": {
            gid: {
                "intro_in_story":  attrs[gid]["intro_in_story"],
                "last_seen_story": attrs[gid]["last_seen_story"],
            }
            for gid in sorted(attrs.keys())
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
    print(f"Wrote {payload['n_introduced']} grammar attributions to:")
    print(f"  {a}")
    print(f"  {b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
