#!/usr/bin/env python3
"""Concrete literary palette for the next (or any) story.

The single highest-leverage v2 tool. Given a story id (or "next"), produces
the **palette** the agent author can use, grouped by sensory category and
flagged by reinforcement debt. The agent reads the JSON; humans can ask for
`--format human` for an eyeball view.

Why this exists
---------------
The 2026-04-27 audit (`docs/archive/audit-2026-04-27.md`) showed defective stories
clustered where the author had no concrete language for the scene they wanted
to write. Authors default to top-of-mind nouns (rain, cat, window, letter)
and grammatical filler (静か, 思います) when nothing concrete is in budget.

A grouped palette with reinforcement-debt stars makes the *available*
concrete language obvious, and nudges the author toward variety AND
pedagogical health simultaneously.

Categories
----------
The palette groups by surface-level semantic category derived from a
small static taxonomy (see `_LEMMA_CATEGORIES` below). New vocabulary
inherits the "uncategorized" bucket until the taxonomy is updated; this
is intentional — the taxonomy is a curation artifact, not a derived one.

Stars
-----
  ★   = "due" — last appeared ≥ N stories ago (default N=8); the author
        SHOULD use this word in the next 1–2 stories
  ★★  = "critical" — last appeared ≥ N+8 stories ago; failure to use this
        soon will trigger a reinforcement-cadence error
  (no star) = recently used; available but not pedagogically pressing

Examples
--------
  palette.py next                    # palette for the next story (id = max+1)
  palette.py 11                      # palette as it would be for story 11
  palette.py 11 --format human       # pretty terminal output
  palette.py 11 --include-grammar    # also list available grammar points
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from typing import Iterable

from _common import (  # noqa: E402
    color,
    iter_stories,
    iter_tokens,
    load_grammar,
    load_vocab_attributed,
    parse_id_arg,
)


# ── Static taxonomy (curated; expand as vocab grows) ─────────────────────────
#
# Each lemma maps to ONE category. Words not in the map go to "uncategorized"
# in the JSON output; the human view drops them so the author can browse.
# Update this map when new vocabulary lands.
_LEMMA_CATEGORIES: dict[str, str] = {
    # ─ places ─
    "公園": "place", "家": "place", "道": "place", "駅": "place",
    "部屋": "place", "庭": "place", "店": "place", "学校": "place",
    "ベンチ": "place", "外": "place", "玄関": "place", "店内": "place",
    # ─ objects ─
    "本": "object", "椅子": "object", "皿": "object", "ペン": "object",
    "手紙": "object", "ドア": "object", "窓": "object", "鍵": "object",
    "箱": "object", "机": "object", "卵": "object", "パン": "object",
    "お茶": "object", "朝ご飯": "object", "石": "object", "木": "object",
    "写真": "object", "音楽": "object", "歌": "object", "時計": "object",
    # ─ beings ─
    "私": "being", "友達": "being", "猫": "being", "犬": "being",
    "鳥": "being", "二人": "being", "母": "being", "父": "being",
    "家族": "being", "学校": "being", "人": "being",
    # ─ time / scene ─
    "朝": "time", "今朝": "time", "夕方": "time", "夜": "time",
    "雨": "weather", "風": "weather", "雪": "weather", "空": "weather",
    "月": "weather", "星": "weather", "春": "season", "夏": "season",
    "秋": "season", "冬": "season",
    # ─ adjectives by axis ─
    "小さい": "size", "大きい": "size",
    "赤い": "color", "白い": "color", "黄色い": "color", "青い": "color",
    "暖かい": "temperature", "寒い": "temperature", "暑い": "temperature",
    "冷たい": "temperature",
    "明るい": "light", "静か": "light",  # 静か is a "mood/light" cousin
    "いい": "evaluative", "嬉しい": "evaluative", "美しい": "evaluative",
    "新しい": "evaluative", "古い": "evaluative", "優しい": "evaluative",
    # ─ verbs by mode ─
    "歩きます": "locomotion", "帰ります": "locomotion", "来ます": "locomotion",
    "立ちます": "locomotion",
    "持ちます": "handling", "置きます": "handling", "開けます": "handling",
    "座ります": "posture", "寝ます": "posture", "休みます": "posture",
    "言います": "speech", "話します": "speech",
    "見ます": "perception", "聞きます": "perception",
    "飲みます": "consumption", "食べます": "consumption",
    "書きます": "production",
    "あります": "existence", "います": "existence",
    "濡れる": "state-change",
    # ─ abstracts ─
    "気分": "abstract", "色": "abstract", "音": "abstract",
    "気持ち": "abstract", "思い出": "abstract", "約束": "abstract",
    "仕事": "abstract", "名前": "abstract",
}

# Display order for the human view; JSON output uses these as keys too.
_CATEGORY_ORDER = [
    "place", "object", "being", "time", "weather", "season",
    "size", "color", "temperature", "light", "evaluative",
    "locomotion", "handling", "posture", "speech", "perception",
    "consumption", "production", "existence", "state-change",
    "abstract", "uncategorized",
]


# ── Reinforcement-debt scoring ───────────────────────────────────────────────
#
# A word's "debt" is measured by how many stories ago it was last used.
# Configurable thresholds:
DUE_AFTER_STORIES = 8       # ★
CRITICAL_AFTER_STORIES = 16  # ★★


def _last_use_by_wid(stories: Iterable[tuple[int, dict]]) -> dict[str, int]:
    """For each word_id, return the highest story id it appeared in."""
    last: dict[str, int] = {}
    for sid, story in stories:
        for tok in iter_tokens(story):
            wid = tok.get("word_id")
            if wid:
                last[wid] = max(last.get(wid, -1), sid)
    return last


def _star_for(wid: str, target_story: int, last_use: dict[str, int]) -> str:
    """Return '', '★', or '★★' for this word at this story id."""
    if wid not in last_use:
        return ""  # never used → not in scope; only "available" words get stars
    gap = target_story - last_use[wid]
    if gap >= CRITICAL_AFTER_STORIES:
        return "★★"
    if gap >= DUE_AFTER_STORIES:
        return "★"
    return ""


# ── Palette construction ─────────────────────────────────────────────────────

def build_palette(target_story: int) -> dict:
    """Build the palette JSON for a given target story id.

    The palette includes EVERY word whose `first_story` <= target_story,
    grouped by `_LEMMA_CATEGORIES`. Each entry has the lemma, word id,
    pos, last_use story (or null), and reinforcement-debt star.
    """
    vocab = load_vocab_attributed()
    stories = list(iter_stories())
    last_use = _last_use_by_wid(stories)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for wid, w in vocab["words"].items():
        first_raw = w.get("first_story")
        if first_raw is None:
            continue
        try:
            first = parse_id_arg(first_raw)
        except (TypeError, ValueError):
            continue
        if first > target_story:
            continue  # not yet in budget at this story
        # Prefer the human-friendly surface as the lemma label
        lemma = w.get("surface") or w.get("kana") or w.get("reading") or wid
        cat = _LEMMA_CATEGORIES.get(lemma, "uncategorized")
        grouped[cat].append({
            "word_id": wid,
            "lemma": lemma,
            "kana": w.get("kana"),
            "reading": w.get("reading"),
            "pos": w.get("pos"),
            "first_story": first,
            "last_use": last_use.get(wid),
            "occurrences": w.get("occurrences", 0),
            "meanings": w.get("meanings") or [],
            "star": _star_for(wid, target_story, last_use),
        })

    # Stable order within each category: most-overdue first, then by lemma.
    def _sort_key(e):
        # "★★" > "★" > "" — sort overdue to top.
        rank = {"★★": 0, "★": 1, "": 2}[e["star"]]
        return (rank, -((e["last_use"] or -1) - target_story), e["lemma"])

    for cat in grouped:
        grouped[cat].sort(key=_sort_key)

    # Materialise category order, dropping empty categories.
    ordered = {
        cat: grouped[cat]
        for cat in _CATEGORY_ORDER
        if cat in grouped and grouped[cat]
    }

    return {
        "target_story": target_story,
        "thresholds": {
            "due_after_stories": DUE_AFTER_STORIES,
            "critical_after_stories": CRITICAL_AFTER_STORIES,
        },
        "categories": ordered,
        "summary": {
            "total_available_words": sum(len(v) for v in ordered.values()),
            "due_count": sum(1 for v in ordered.values() for e in v if e["star"] == "★"),
            "critical_count": sum(1 for v in ordered.values() for e in v if e["star"] == "★★"),
        },
    }


# ── Grammar inclusion (optional) ─────────────────────────────────────────────

def build_grammar_palette(target_story: int) -> list[dict]:
    """All grammar points whose intro_in_story <= target_story.

    Phase A derive-on-read (2026-05-01): intro_in_story and last_use are
    both derived from corpus first/last appearance, not from stored
    state fields. last_use here is identical to derive_grammar_attributions()
    last_seen_story but kept as a separate name for output-schema stability.
    """
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
    from derived_state import derive_grammar_attributions  # noqa: E402

    grammar = load_grammar()
    attributions = derive_grammar_attributions()

    out = []
    for gid, p in grammar.get("points", {}).items():
        attr = attributions.get(gid)
        if attr is None:
            continue
        intro = attr["intro_in_story"]
        if intro is None or intro > target_story:
            continue
        out.append({
            "grammar_id": gid,
            "label": p.get("label") or p.get("name"),
            "intro_in_story": intro,
            "last_use": attr["last_seen_story"],
        })
    out.sort(key=lambda e: (e["last_use"] or -1, e["grammar_id"]))
    return out


# ── CLI ──────────────────────────────────────────────────────────────────────

def _next_story_id() -> int:
    last = max((sid for sid, _ in iter_stories()), default=0)
    return last + 1


def _parse_target(arg: str) -> int:
    if arg == "next":
        return _next_story_id()
    return parse_id_arg(arg)


def _format_human(palette: dict, grammar: list[dict] | None) -> str:
    lines = []
    t = palette["target_story"]
    s = palette["summary"]
    lines.append(color(f"PALETTE for story {t}", "bold"))
    lines.append(
        f"  available: {s['total_available_words']} words   "
        f"due: {s['due_count']}   critical: {s['critical_count']}"
    )
    lines.append(
        color(
            f"  ★  = unused for ≥{palette['thresholds']['due_after_stories']} stories   "
            f"★★ = ≥{palette['thresholds']['critical_after_stories']} stories",
            "dim",
        )
    )
    for cat, entries in palette["categories"].items():
        if cat == "uncategorized":
            continue  # noise for the human view
        lines.append("")
        lines.append(color(f"  {cat}", "cyan"))
        chunks = []
        for e in entries:
            star = e["star"]
            if star == "★★":
                lemma = color(e["lemma"], "red")
            elif star == "★":
                lemma = color(e["lemma"], "yellow")
            else:
                lemma = e["lemma"]
            label = f"{lemma}{star}" if star else lemma
            chunks.append(label)
        # Wrap to ~80 cols
        line = "    "
        for c in chunks:
            if len(line) + len(c) > 78:
                lines.append(line.rstrip())
                line = "    "
            line += c + "  "
        if line.strip():
            lines.append(line.rstrip())
    if grammar:
        lines.append("")
        lines.append(color("  grammar points active", "cyan"))
        for g in grammar:
            lines.append(
                f"    {g['grammar_id']:<22s} {g.get('label') or '-':<28s} "
                f"last_use={g['last_use'] or '-'}"
            )
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("target", help="story id, 'story_N', or 'next'")
    p.add_argument("--format", choices=("json", "human"), default="json")
    p.add_argument("--include-grammar", action="store_true")
    args = p.parse_args()

    target = _parse_target(args.target)
    palette = build_palette(target)
    grammar = build_grammar_palette(target) if args.include_grammar else None
    if args.include_grammar:
        palette["grammar_points"] = grammar

    if args.format == "json":
        print(json.dumps(palette, ensure_ascii=False, indent=2))
    else:
        print(_format_human(palette, grammar))


if __name__ == "__main__":
    main()
