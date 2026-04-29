#!/usr/bin/env python3
"""forbid.py — mechanical "forbidden zones" for the next story.

Walks the existing corpus and prints, for the given story id N, the
narrow set of scene/anchor/opening/closer shapes that the agent must
avoid this story unless it has a deliberate, documented reason. The
output is meant to be pasted verbatim into the spec's `intent` block
under a `FORBIDDEN THIS STORY:` heading so the constraints become a
visible contract before any JP is drafted.

Usage:
    python3 pipeline/tools/forbid.py N            # for story N
    python3 pipeline/tools/forbid.py next         # for max(existing)+1
    python3 pipeline/tools/forbid.py N --json     # machine-readable output

The four computed zones (configurable via constants below):

  1. scene_class       — every value used by stories N-3..N-1
  2. anchor_object     — every anchor used by stories N-5..N-1
  3. opening_token_seq — first 3 content tokens of stories N-3..N-1
  4. closer_shape      — POS/grammar shape of the closer of stories N-3..N-1

This tool is purely descriptive — it never edits files, never calls an
LLM, never blocks. It exists so the agent's own discipline (per the
SKILL §B.1) has concrete numbers to respect, not vibes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the pipeline package importable when this file is run as a script.
_PIPELINE = Path(__file__).resolve().parents[1]
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

from _paths import (  # noqa: E402
    iter_stories,
    iter_specs,
    list_story_ids,
    parse_story_id,
)

# ── Window sizes (tune here, NOT in the SKILL) ──────────────────────────────
SCENE_LOOKBACK = 3
ANCHOR_LOOKBACK = 5
OPENING_LOOKBACK = 3
CLOSER_LOOKBACK = 3
OPENING_TOKEN_PREFIX = 3   # first K content tokens of s0 to fingerprint


# ── Shape extraction ────────────────────────────────────────────────────────

def _content_tokens(sentence: dict) -> list[dict]:
    return [t for t in (sentence.get("tokens") or [])
            if t.get("role") == "content"]


def _opening_seq(story: dict) -> list[str]:
    """First K content surface tokens of sentence 0, or [] if absent."""
    sentences = story.get("sentences") or []
    if not sentences:
        return []
    toks = _content_tokens(sentences[0])
    return [t.get("t", "") for t in toks[:OPENING_TOKEN_PREFIX]]


def _closer_shape(story: dict) -> str:
    """Coarse shape fingerprint for the final sentence.

    We DON'T fingerprint surface tokens (those vary across stories
    legitimately). We DO fingerprint the sequence of {role, particle,
    inflection-class} so a 「Nは i-adj です」 closer collides with another
    「Nは i-adj です」 closer regardless of which noun/adjective is used.

    Returned shape strings look like:
        "noun-WA-iadj-DESU"        ← 「箱は重いです」 / 「紙は古いです」
        "noun-WA-naadj-DESU"       ← 「窓は明るいです」 (na-adj path)
        "noun-NI-noun-GA-aru"      ← 「道に花があります」
        "noun-WO-verb_masu"        ← 「私は紙を読みます」
        "verb_te-verb_masu"        ← 「鍵を取って、箱を開けます」
        "noun-KARA-DESU"           ← 「紙は友達からです」
        "<other>"                  ← anything not in the curated table

    The table is intentionally small: it covers the closer shapes that
    have already been observed (and over-used) in stories 1..10, so
    the lookup mechanically catches the actual repetition pattern,
    not hypothetical shapes.
    """
    sentences = story.get("sentences") or []
    if not sentences:
        return "<empty>"
    toks = sentences[-1].get("tokens") or []
    if not toks:
        return "<empty>"

    sig: list[str] = []
    for t in toks:
        role = t.get("role")
        if role == "punct":
            continue
        if role == "particle":
            surface = t.get("t", "")
            sig.append({
                "は": "WA", "が": "GA", "を": "WO", "に": "NI",
                "で": "DE", "と": "TO", "の": "NO", "から": "KARA",
                "へ": "E", "や": "YA", "も": "MO",
            }.get(surface, f"P:{surface}"))
            continue
        if role == "content":
            pos = t.get("pos") or ""
            adj_class = t.get("adj_class")
            verb_class = t.get("verb_class")
            inflection = (t.get("inflection") or {}).get("form") or ""
            if pos.startswith("verb") or verb_class:
                if "te" in inflection:
                    sig.append("verb_te")
                elif "masu" in inflection or inflection == "":
                    sig.append("verb_masu")
                else:
                    sig.append(f"verb_{inflection or 'plain'}")
                continue
            if pos == "i_adj" or adj_class == "i":
                sig.append("iadj")
                continue
            if pos == "na_adj" or adj_class == "na":
                sig.append("naadj")
                continue
            if "aru" in (t.get("t") or "") or "いる" in (t.get("t") or ""):
                sig.append("aru")
                continue
            sig.append("noun")
            continue
        # copula / aux / other
        surface = t.get("t", "")
        if surface in ("です", "だ"):
            sig.append("DESU")
            continue
        sig.append(f"X:{surface}")

    return "-".join(sig) if sig else "<empty>"


def _scene_anchor(story_or_spec: dict) -> tuple[str | None, str | None]:
    """Return (scene_class, anchor_object) from a story OR a spec."""
    return (
        story_or_spec.get("scene_class"),
        story_or_spec.get("anchor_object"),
    )


# ── Zone computation ────────────────────────────────────────────────────────

def _load_corpus_by_id() -> dict[int, dict]:
    """All shipped stories, keyed by id."""
    return {sid: s for sid, s in iter_stories()}


def _load_specs_by_id() -> dict[int, dict]:
    """All specs (authoritative source for scene_class/anchor_object)."""
    out: dict[int, dict] = {}
    for sid, spec in iter_specs():
        out[sid] = spec
    return out


def compute_forbidden(target_story: int) -> dict:
    """Compute the four forbidden zones for `target_story`.

    Returns a dict with sub-keys per zone, each carrying both the
    forbidden values AND the (story_id, evidence) sources so the agent
    can sanity-check them.
    """
    stories = _load_corpus_by_id()
    specs = _load_specs_by_id()

    def _meta_for(sid: int) -> dict:
        """Prefer the spec (richer metadata); fall back to the built story."""
        return specs.get(sid) or stories.get(sid) or {}

    # Scene zone.
    scene_zone: list[dict] = []
    for sid in range(target_story - SCENE_LOOKBACK, target_story):
        meta = _meta_for(sid)
        sc, _ = _scene_anchor(meta)
        if sc:
            scene_zone.append({"story_id": sid, "scene_class": sc})

    # Anchor zone.
    anchor_zone: list[dict] = []
    for sid in range(target_story - ANCHOR_LOOKBACK, target_story):
        meta = _meta_for(sid)
        _, anc = _scene_anchor(meta)
        if anc:
            anchor_zone.append({"story_id": sid, "anchor_object": anc})

    # Opening zone — must read the BUILT story for token roles.
    opening_zone: list[dict] = []
    for sid in range(target_story - OPENING_LOOKBACK, target_story):
        story = stories.get(sid)
        if not story:
            continue
        seq = _opening_seq(story)
        if seq:
            opening_zone.append({"story_id": sid, "opening_seq": seq})

    # Closer zone.
    closer_zone: list[dict] = []
    for sid in range(target_story - CLOSER_LOOKBACK, target_story):
        story = stories.get(sid)
        if not story:
            continue
        shape = _closer_shape(story)
        sentences = story.get("sentences") or []
        surface = ""
        if sentences:
            surface = "".join(t.get("t", "") for t in (sentences[-1].get("tokens") or []))
        closer_zone.append({
            "story_id": sid,
            "shape": shape,
            "surface_evidence": surface,
        })

    return {
        "target_story": target_story,
        "windows": {
            "scene": SCENE_LOOKBACK,
            "anchor": ANCHOR_LOOKBACK,
            "opening": OPENING_LOOKBACK,
            "closer": CLOSER_LOOKBACK,
        },
        "scene_zone": scene_zone,
        "anchor_zone": anchor_zone,
        "opening_zone": opening_zone,
        "closer_zone": closer_zone,
        "summary": {
            "forbidden_scenes":  sorted({z["scene_class"]   for z in scene_zone}),
            "forbidden_anchors": sorted({z["anchor_object"] for z in anchor_zone}),
            "forbidden_opening_seqs": [z["opening_seq"] for z in opening_zone],
            "forbidden_closer_shapes": sorted({z["shape"] for z in closer_zone}),
        },
    }


# ── Rendering ───────────────────────────────────────────────────────────────

def render_human(zones: dict) -> str:
    n = zones["target_story"]
    w = zones["windows"]
    lines: list[str] = []
    lines.append(f"FORBIDDEN ZONES for story {n}")
    lines.append("─" * 60)
    lines.append("(Paste the SUMMARY block into your spec's `intent` field, "
                 "verbatim, before drafting.)")
    lines.append("")

    s = zones["summary"]
    lines.append(f"SUMMARY:")
    lines.append(f"  scene_class    (last {w['scene']} stories): "
                 f"{', '.join(s['forbidden_scenes']) or '(none yet)'}")
    lines.append(f"  anchor_object  (last {w['anchor']} stories): "
                 f"{', '.join(s['forbidden_anchors']) or '(none yet)'}")
    lines.append(f"  closer_shape   (last {w['closer']} stories): "
                 f"{', '.join(s['forbidden_closer_shapes']) or '(none yet)'}")
    lines.append(f"  opening_seqs   (last {w['opening']} stories' first 3 "
                 f"content tokens):")
    for seq in s["forbidden_opening_seqs"]:
        lines.append(f"    - {' / '.join(seq)}")
    if not s["forbidden_opening_seqs"]:
        lines.append(f"    (none yet)")

    lines.append("")
    lines.append("EVIDENCE (for sanity-check; NOT to paste into the spec):")
    for z in zones["scene_zone"]:
        lines.append(f"  scene  story {z['story_id']:>2}: "
                     f"{z['scene_class']}")
    for z in zones["anchor_zone"]:
        lines.append(f"  anchor story {z['story_id']:>2}: "
                     f"{z['anchor_object']}")
    for z in zones["opening_zone"]:
        lines.append(f"  open   story {z['story_id']:>2}: "
                     f"{' / '.join(z['opening_seq'])}")
    for z in zones["closer_zone"]:
        lines.append(f"  close  story {z['story_id']:>2}: "
                     f"{z['shape']}  ({z['surface_evidence']})")

    lines.append("")
    lines.append("RULES:")
    lines.append("  - Avoid every value above unless your spec's `intent` "
                 "documents WHY a deliberate exception is needed.")
    lines.append("  - Each documented exception counts toward the per-session "
                 "override budget (max 1; see SKILL §G).")
    return "\n".join(lines)


# ── CLI ─────────────────────────────────────────────────────────────────────

def _resolve_target(arg: str) -> int:
    if arg in ("next", "auto"):
        ids = list_story_ids()
        return (max(ids) + 1) if ids else 1
    return parse_story_id(arg)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    p.add_argument("target", help='story id (int) or "next"')
    p.add_argument("--json", action="store_true", help="emit JSON instead")
    args = p.parse_args()

    target = _resolve_target(args.target)
    zones = compute_forbidden(target)

    if args.json:
        print(json.dumps(zones, ensure_ascii=False, indent=2))
    else:
        print(render_human(zones))


if __name__ == "__main__":
    main()
