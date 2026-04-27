#!/usr/bin/env python3
"""
Monogatari — Vocab shard builder.

Splits `data/vocab_state.json` into a small reader-friendly index plus
content-addressed payload shards. The reader loads the index at boot
(small, fast); shards are fetched lazily when a popup needs full word
detail.

Layout:

    data/vocab/
      index.json                 # one row per word: id, surface, kana, reading,
                                 # short meaning, status hints, shard pointer
      shards/
        00.json
        01.json
        ...
        FF.json                  # 256 shards keyed by first byte of sha1(id)

A shard contains:
    {
      "version": 1,
      "shard": "3a",
      "words": {
        "W00042": { ...full record... },
        ...
      }
    }

Shard count is fixed at 256 so the reader's URL math is trivial. At
~18,000 words this gives ~70 words per shard; at ~50,000 words ~200 per
shard. Each shard stays well under 100 KB even at corpus scale.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

SHARD_BITS = 8  # 256 shards
SHARD_HEX_WIDTH = SHARD_BITS // 4  # 2 hex chars


def shard_key_for(word_id: str) -> str:
    """Returns the 2-hex-char shard key for a word id."""
    h = hashlib.sha1(word_id.encode("utf-8")).hexdigest()
    return h[:SHARD_HEX_WIDTH]


def build(vocab: dict) -> tuple[dict, dict[str, dict]]:
    index_rows: list[dict] = []
    shards: dict[str, dict] = defaultdict(lambda: {"version": 1, "shard": "", "words": {}})

    for wid, w in vocab.get("words", {}).items():
        shard = shard_key_for(wid)
        shards[shard]["shard"] = shard
        shards[shard]["words"][wid] = w
        index_rows.append(
            {
                "id": wid,
                "shard": shard,
                "surface": w.get("surface", ""),
                "kana": w.get("kana", ""),
                "reading": w.get("reading", ""),
                # First meaning only — the popup loads the full record from the shard.
                "short_meaning": (w.get("meanings") or [""])[0],
                "first_story": w.get("first_story"),
                "occurrences": w.get("occurrences", 0),
            }
        )

    index_rows.sort(key=lambda r: r["id"])

    index = {
        "version": vocab.get("version", 1),
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "shard_bits": SHARD_BITS,
        "shard_count": 1 << SHARD_BITS,
        "next_word_id": vocab.get("next_word_id"),
        "last_story_id": vocab.get("last_story_id"),
        "n_words": len(index_rows),
        "words": index_rows,
    }
    return index, dict(shards)


def main() -> None:
    src = Path("data/vocab_state.json")
    if not src.exists():
        print(f"ERROR: {src} not found", file=sys.stderr)
        sys.exit(1)

    vocab = json.loads(src.read_text(encoding="utf-8"))
    index, shards = build(vocab)

    out_dir = Path("data/vocab")
    shard_dir = out_dir / "shards"
    shard_dir.mkdir(parents=True, exist_ok=True)

    # Wipe stale shards
    for f in shard_dir.glob("*.json"):
        f.unlink()

    (out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for shard, payload in shards.items():
        (shard_dir / f"{shard}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    sizes = {p.stat().st_size for p in shard_dir.glob("*.json")}
    print(
        f"✓ Wrote {out_dir}/index.json ({(out_dir / 'index.json').stat().st_size} B) "
        f"+ {len(shards)} shards (sizes: {min(sizes) if sizes else 0}-{max(sizes) if sizes else 0} B)"
    )


if __name__ == "__main__":
    main()
