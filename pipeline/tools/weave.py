#!/usr/bin/env python3
"""Assisted reinforcement weaving.

Reads cadence violations and produces a YAML/JSON weave plan that can be
edited by hand before applying. The plan format is intentionally simple:

  - story: 18                  # target story
    jp: "..."                  # JP sentence to append
    en: "..."                  # EN gloss
  - story: 19
    replace: 5                 # optional: replace sentence index 5 instead
    jp: "..."
    en: "..."

Examples:
  weave.py suggest               # prints a starter plan to stdout
  weave.py apply plan.json       # validate then apply (no regen — call regen.py)
  weave.py apply plan.json --regen   # apply + full regen + validate
  weave.py preview plan.json     # show what each weave will tokenize to
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys

from _common import (load_spec, save_spec, load_vocab, load_grammar,
                     iter_stories, build, color, ROOT)


def _word_ids_used(story: dict) -> set[str]:
    used = set()
    for sec in ("title",):
        for tok in (story.get(sec) or {}).get("tokens", []):
            if tok.get("word_id"):
                used.add(tok["word_id"])
    for sn in story.get("sentences", []):
        for tok in sn.get("tokens", []):
            if tok.get("word_id"):
                used.add(tok["word_id"])
    return used


def _grammar_ids_used(story: dict) -> set[str]:
    used = set()
    for sec in ("title",):
        for tok in (story.get(sec) or {}).get("tokens", []):
            if tok.get("grammar_id"):
                used.add(tok["grammar_id"])
    for sn in story.get("sentences", []):
        for tok in sn.get("tokens", []):
            if tok.get("grammar_id"):
                used.add(tok["grammar_id"])
    return used


def cmd_suggest(args):
    """Print a starter weave plan: one stub per R1, R2, or G2 violation."""
    sys.path.insert(0, str(ROOT / "pipeline"))
    # VOCAB_MAX_GAP, VOCAB_ABANDON_GRACE were used by the R2 weave — retired 2026-04-24.
    from grammar_progression import (BOOTSTRAP_END, VOCAB_REINFORCE_WINDOW,
                                     VOCAB_REINFORCE_MIN_USES,
                                     REINFORCEMENT_WINDOW, MIN_REINFORCEMENT_USES)
    by_n = {sid: s for sid, s in iter_stories()}
    used = {n: _word_ids_used(s) for n, s in by_n.items()}
    used_g = {n: _grammar_ids_used(s) for n, s in by_n.items()}
    vocab = load_vocab()
    grammar = load_grammar()
    plan = []
    rules = set(args.rules or ["r1", "r2", "g2"])
    max_n = max(by_n)

    if "r1" in rules:
        intros = {}
        for n, s in by_n.items():
            if n <= BOOTSTRAP_END: continue
            ids = [w if isinstance(w, str) else w.get("id") or w.get("word_id", "")
                   for w in (s.get("new_words") or [])]
            intros[n] = [i for i in ids if i]
        for n, ids in intros.items():
            followups = [i for i in range(n+1, n+1+VOCAB_REINFORCE_WINDOW) if i in by_n]
            if len(followups) < VOCAB_REINFORCE_MIN_USES: continue
            required = min(VOCAB_REINFORCE_MIN_USES, len(followups))
            for wid in ids:
                hits = [i for i in followups if wid in used.get(i, set())]
                if len(hits) < required:
                    gap = required - len(hits)
                    w = vocab["words"].get(wid, {})
                    surf = w.get("surface", "?")
                    meaning = (w.get("meanings") or ["?"])[0][:40]
                    target = followups[len(hits)] if len(hits) < len(followups) else followups[0]
                    plan.append({
                        "story": target, "jp": f"# R1 weave {surf} ({meaning}) — gap={gap} (intro story_{n}, wid={wid})",
                        "en": "TODO",
                        "_meta": {"rule": "R1", "violation": f"story_{n} introduced {wid}", "gap": gap},
                    })

    if "r2" in rules:
        # Rule R2 (vocab abandonment) was retired on 2026-04-24 — see
        # test_no_vocab_word_abandoned for the rationale. Late reuse is
        # encouraged but not required, so there are no R2 violations to
        # weave for. Kept here as a no-op so existing scripts that pass
        # `--rules r1,r2,g2` continue to work.
        pass

    if "g2" in rules:
        intros_g = {}
        for n, s in by_n.items():
            ids = [g if isinstance(g, str) else g.get("id") for g in (s.get("new_grammar") or [])]
            intros_g[n] = [i for i in ids if i]
        for n, ids in intros_g.items():
            followups = [i for i in range(n+1, n+1+REINFORCEMENT_WINDOW) if i in by_n]
            if not followups: continue
            required = min(MIN_REINFORCEMENT_USES, len(followups))
            for gid in ids:
                hits = [i for i in followups if gid in used_g.get(i, set())]
                if len(hits) < required:
                    g = grammar["points"].get(gid, {})
                    plan.append({
                        "story": followups[0],
                        "jp": f"# G2 weave {gid} ({g.get('title','?')}) — needed (intro story_{n})",
                        "en": "TODO",
                        "_meta": {"rule": "G2", "gid": gid, "intro": n},
                    })

    print(json.dumps(plan, ensure_ascii=False, indent=2))


def _load_plan(path):
    with open(path) as f:
        text = f.read()
    if path.endswith(".json"):
        return json.loads(text)
    # naive YAML fallback (only flat lists of dicts)
    raise SystemExit("Only JSON plans supported (got " + path + ")")


def cmd_preview(args):
    plan = _load_plan(args.plan)
    vocab = load_vocab(); grammar = load_grammar()
    for entry in plan:
        sid = entry["story"]
        if entry.get("jp", "").lstrip().startswith("#"):
            continue
        spec = {"story_id": 999, "title": {"jp": entry["jp"], "en": "preview"},
                "sentences": [{"jp": entry["jp"], "en": entry.get("en","")}]}
        story, report = build(spec, vocab, grammar)
        mints = report.get("new_words") or []
        marker = color(f"MINTS {len(mints)}", "red") if mints else color("clean", "green")
        print(f"  story_{sid}: {marker}  {entry['jp']}")
        for nw in mints:
            print(f"    NEW: {nw}")


def cmd_apply(args):
    plan = _load_plan(args.plan)
    grouped: dict[int, list[dict]] = {}
    for entry in plan:
        if entry.get("jp", "").lstrip().startswith("#"):
            continue
        grouped.setdefault(entry["story"], []).append(entry)
    for sid, entries in grouped.items():
        spec = load_spec(sid)
        spec.setdefault("sentences", [])
        for e in entries:
            sn = {"jp": e["jp"], "en": e.get("en", "")}
            if "replace" in e:
                idx = int(e["replace"])
                spec["sentences"][idx] = sn
                action = f"replace:{idx}"
            else:
                spec["sentences"].append(sn)
                action = f"append:{len(spec['sentences'])-1}"
            print(color(f"  story_{sid} {action}: {sn['jp']}", "green"))
        save_spec(sid, spec)
    if args.regen:
        subprocess.run([sys.executable, "pipeline/regenerate_all_stories.py", "--apply"],
                       cwd=ROOT)
        subprocess.run([sys.executable, "pipeline/tools/cadence.py", "validate"],
                       cwd=ROOT)


def main():
    p = argparse.ArgumentParser(prog="weave.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("suggest", help="auto-draft a plan from current violations")
    s.add_argument("--rules", nargs="+", choices=["r1", "r2", "g2"],
                   help="restrict to specific rule(s); default: all three")
    s.set_defaults(func=cmd_suggest)
    s = sub.add_parser("preview"); s.add_argument("plan"); s.set_defaults(func=cmd_preview)
    s = sub.add_parser("apply"); s.add_argument("plan")
    s.add_argument("--regen", action="store_true",
                   help="run full library regen + validate after applying")
    s.set_defaults(func=cmd_apply)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
