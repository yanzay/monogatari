#!/usr/bin/env python3
"""
normalize_to_v2.py — bring all shipped stories to the v2 token-schema baseline.

Picks the dominant schema convention used in the existing 67-story library
and rewrites the v1/v3 outliers in place. Designed to be idempotent.

Transformations applied per token:

  1. inflection.form: rename redundant aliases
        masu_polite_nonpast    → polite_nonpast
        masu_polite_past       → polite_past
        masu_polite_negative   → negative_polite
        te_form                → te
     (plain_nonpast / plain_past stay — they're real distinct forms.)

  2. inflection.grammar_id → token.grammar_id
        Move the field out of `inflection` and onto the token itself,
        unless the token already has a grammar_id (in which case keep
        whichever is non-empty / matches).

  3. v3-slim inflection (only {form, grammar_id}, no base/base_r/verb_class):
        Re-derive `base`, `base_r`, `verb_class` from the token's surface
        using `pipeline.jp.analyze_verb`. If derivation fails, leave as-is
        and report.

  4. Missing verb_class on a verb-bearing inflection block:
        Derive from analyze_verb and add.

Usage:
    python3 pipeline/normalize_to_v2.py --dry-run    # report only
    python3 pipeline/normalize_to_v2.py --apply      # write changes (with backup)
    python3 pipeline/normalize_to_v2.py --story 67   # single-story drilldown
"""
from __future__ import annotations
import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from jp import analyze_verb, JP_OK  # type: ignore
except ImportError:
    JP_OK = False
    analyze_verb = None  # type: ignore


FORM_RENAMES: dict[str, str] = {
    "masu_polite_nonpast":  "polite_nonpast",
    "masu_polite_past":     "polite_past",
    "masu_polite_negative": "negative_polite",
    "te_form":              "te",
}

import re
ROMAJI_RE = re.compile(r"^[a-zA-Z]+$")

try:
    import jaconv  # type: ignore
    def romaji_to_hira(r: str) -> Optional[str]:
        try:
            kana = jaconv.alphabet2kana(r)
            hira = jaconv.kata2hira(kana)
            # Sanity: must be all hiragana
            if all("\u3040" <= ch <= "\u309f" or ch in "ー" for ch in hira):
                return hira
        except Exception:
            return None
        return None
except ImportError:
    def romaji_to_hira(r: str) -> Optional[str]:
        return None


# ── Per-token rewrites ───────────────────────────────────────────────────────

def normalize_token(tok: dict, stats: Counter, surface_warnings: list) -> bool:
    """Rewrite tok IN PLACE. Returns True if anything changed."""
    snapshot = json.dumps(tok, sort_keys=True, ensure_ascii=False)
    changed = False

    # 0. Fix romaji `r` field (e.g. "sagashimasu" → "さがします"). This is a
    #    bona-fide data bug — the schema requires hiragana.
    r = tok.get("r")
    if isinstance(r, str) and ROMAJI_RE.match(r):
        hira = romaji_to_hira(r)
        if hira:
            tok["r"] = hira
            stats[("romaji_to_hira",)] += 1
            changed = True
        else:
            surface_warnings.append({
                "surface": tok.get("t"),
                "issue":   "romaji 'r' could not be converted to kana",
                "r":       r,
            })

    # P3-A. Drop `r` from grammar tokens (aux / particle). Mixed canonical
    # behavior; pick the cleaner / dominant rule of omitting it.
    if tok.get("role") in ("aux", "particle") and "r" in tok:
        # But if the surface differs from r (e.g. でした vs でし+た merge,
        # or compound particles), keep it.
        if tok.get("r") == tok.get("t"):
            del tok["r"]
            stats[("drop_r_from_grammar_token",)] += 1
            changed = True

    # P3-B. Force そして role → particle (dominant 12/18; rest were aux).
    if tok.get("t") == "そして" and tok.get("role") == "aux":
        tok["role"] = "particle"
        stats[("normalize_role_soshite",)] += 1
        changed = True

    # P3-C. Force な (na-adj suffix) role → particle when it has the
    # G016_na_adjective tag.
    if (tok.get("t") == "な"
        and tok.get("role") == "aux"
        and tok.get("grammar_id") == "G016_na_adjective"):
        tok["role"] = "particle"
        stats[("normalize_role_na",)] += 1
        changed = True

    # P3-D. Split 静かな → 静か + な (split is 54:4 dominant). When we see a
    # token whose surface is exactly 静かな, replace it with 静か (keeping
    # everything else) and append a な particle token immediately after.
    # NOTE: this MUST be done at the section level (we need to insert a token).
    # We mark it here for the section pass to handle.
    if tok.get("t") == "静かな" and tok.get("role") == "content":
        tok["_split_shizukana"] = True
        stats[("mark_split_shizukana",)] += 1
        changed = True

    # P3-E. Collapse G023_attributive → G022_i_adj. Both tag the same
    # syntactic phenomenon (i-adjective in dictionary form); the canonical
    # library oscillates between them inconsistently.
    if tok.get("grammar_id") == "G023_attributive":
        tok["grammar_id"] = "G022_i_adj"
        stats[("collapse_g023_to_g022",)] += 1
        changed = True
    inf_for_g023 = tok.get("inflection")
    if isinstance(inf_for_g023, dict) and inf_for_g023.get("grammar_id") == "G023_attributive":
        inf_for_g023["grammar_id"] = "G022_i_adj"
        stats[("collapse_g023_to_g022",)] += 1
        changed = True

    inf = tok.get("inflection")
    if not isinstance(inf, dict):
        return changed

    # Snapshot original form for possible revert.
    original_form = inf.get("form")

    # 1. Rename form aliases
    form = inf.get("form")
    if form in FORM_RENAMES:
        inf["form"] = FORM_RENAMES[form]
        stats[("rename_form", form, inf["form"])] += 1
        changed = True

    # 2. Move grammar_id from inflection → token (only when safe).
    if "grammar_id" in inf:
        inner_gid = inf.get("grammar_id")
        outer_gid = tok.get("grammar_id")
        if outer_gid and inner_gid and outer_gid != inner_gid:
            # Conflict: leave both in place. The inner grammar_id encodes a
            # higher-level pattern (e.g. G041_masenka_invitation,
            # G056_plain_past_pair) that's distinct from the inflection
            # grammar (G036_masen / G013_mashita_past). Preserve information.
            surface_warnings.append({
                "surface": tok.get("t"),
                "issue":   "grammar_id conflict (outer vs inner) — left in place",
                "outer":   outer_gid,
                "inner":   inner_gid,
            })
        else:
            # Safe to move: outer is missing or equal. Drop inner.
            inf.pop("grammar_id")
            if inner_gid and not outer_gid:
                tok["grammar_id"] = inner_gid
            stats[("move_grammar_id_to_token",)] += 1
            changed = True

    # 3 / 4. Re-derive base/base_r/verb_class for verbs whose inflection block
    #        is v3-slim (missing those fields).
    surface = tok.get("t") or ""
    has_base    = "base" in inf
    has_base_r  = "base_r" in inf
    has_vclass  = "verb_class" in inf
    looks_verb  = inf.get("form") in (
        "polite_nonpast", "polite_past", "negative_polite",
        "negative_polite_past", "te", "past", "negative", "dictionary",
        "plain_nonpast", "plain_past",
    )
    # Only attempt re-derivation when it actually looks like a verb token
    # (skip i-adj / na-adj which carry inflection of form 'plain_nonpast' but
    # have no analyze_verb match).
    if looks_verb and not (has_base and has_base_r and has_vclass):
        if JP_OK:
            info = analyze_verb(surface) or {}
            if info:
                # If the token has a kana `r` reading, sanity-check the
                # auto-derived base against it. UniDic homographs (e.g. 降る
                # vs 下りる for 降ります) can produce a base whose dict-form
                # kana doesn't match the token's actual reading.
                tok_r = tok.get("r")
                derived_base_kana = _dict_form_kana(info) or ""
                base_matches_r = True
                if tok_r and isinstance(tok_r, str) and derived_base_kana:
                    # Strip the masu/te/ta suffix from the token reading and
                    # compare the verb-stem portion to the derived base.
                    base_stem = derived_base_kana[:-1] if len(derived_base_kana) > 1 else derived_base_kana
                    if not tok_r.startswith(base_stem):
                        base_matches_r = False
                if not base_matches_r:
                    # UniDic chose a homograph that doesn't match the token's
                    # reading. Try deriving from the reading itself: re-run
                    # analyze_verb on a kana-only synthetic surface = `tok_r`.
                    fallback_info = analyze_verb(tok_r) if tok_r else None
                    if fallback_info and _dict_form_kana(fallback_info) and \
                       _dict_form_kana(fallback_info)[:-1] and \
                       tok_r.startswith(_dict_form_kana(fallback_info)[:-1]):
                        info = fallback_info
                        derived_base_kana = _dict_form_kana(info) or ""
                        # Use the kana base as `base` too — homograph means
                        # we can't be sure of the kanji form.
                        info_base = info.get("lemma") or derived_base_kana
                    else:
                        surface_warnings.append({
                            "surface": surface,
                            "issue":   "auto-derived base does not match token reading; left blank",
                            "derived_base": info.get("lemma"),
                            "derived_base_kana": derived_base_kana,
                            "token_r": tok_r,
                        })
                        info = {}
                        info_base = None
                else:
                    info_base = info.get("lemma")

                if info:
                    if not has_base and info_base:
                        inf["base"] = info_base
                        stats[("derive_base",)] += 1
                        changed = True
                    if not has_vclass and info.get("verb_class"):
                        inf["verb_class"] = info["verb_class"]
                        stats[("derive_verb_class",)] += 1
                        changed = True
                    if not has_base_r and derived_base_kana:
                        inf["base_r"] = derived_base_kana
                        stats[("derive_base_r",)] += 1
                        changed = True

    # Final guard: if we renamed form but couldn't populate base/base_r the
    # validator will mis-conjugate. Revert the rename so the validator skips
    # this token (it ignores unknown form names). Since this puts the token
    # back into its original state for the form field, decrement the
    # `rename_form` stat too and don't claim the file changed *because of*
    # this. Other transformations may still have fired.
    if (
        original_form in FORM_RENAMES
        and inf.get("form") == FORM_RENAMES[original_form]
        and not (inf.get("base") and inf.get("base_r"))
    ):
        inf["form"] = original_form
        # Cancel the matching rename so net token state is unchanged for this field
        rename_key = ("rename_form", original_form, FORM_RENAMES[original_form])
        if stats.get(rename_key, 0) > 0:
            stats[rename_key] -= 1

    # Final idempotency check: if the token's state is identical to the
    # snapshot we took at entry, declare no change. This guards against
    # cancel-pairs (e.g. rename_form + revert_form_rename) marking the file
    # as changed even though nothing was actually rewritten.
    if json.dumps(tok, sort_keys=True, ensure_ascii=False) == snapshot:
        return False

    return changed


# ── Helpers ──────────────────────────────────────────────────────────────────

_GODAN_ENDING: dict[str, str] = {
    "五段-カ行": "く", "五段-ガ行": "ぐ", "五段-サ行": "す", "五段-タ行": "つ",
    "五段-ナ行": "ぬ", "五段-バ行": "ぶ", "五段-マ行": "む", "五段-ラ行": "る",
    "五段-ワア行": "う", "五段-ワ行": "う",
}


def _dict_form_kana(info: dict) -> str:
    """Reconstruct dictionary-form kana from analyze_verb's output."""
    try:
        import jaconv  # type: ignore
        kata2hira = jaconv.kata2hira
    except ImportError:
        kata2hira = lambda s: s  # noqa
    stem = kata2hira(info.get("lemma_kana") or "")
    vc   = info.get("verb_class") or "ichidan"
    conj = info.get("conj_type") or ""
    if not stem:
        return ""
    if vc == "ichidan":
        return stem if stem.endswith("る") else stem + "る"
    if vc == "godan":
        end = _GODAN_ENDING.get(conj)
        if end:
            return stem[:-1] + end
        # Fallback: i-row → u-row
        last = stem[-1]
        i_to_u = {"い":"う","き":"く","ぎ":"ぐ","し":"す","ち":"つ",
                  "に":"ぬ","ひ":"ふ","び":"ぶ","み":"む","り":"る"}
        return stem[:-1] + i_to_u[last] if last in i_to_u else ""
    if vc == "irregular_kuru": return "くる"
    if vc == "irregular_suru": return "する"
    if vc == "irregular_aru":  return "ある"
    return ""


# ── Per-story orchestration ──────────────────────────────────────────────────

def _post_split_shizukana(tokens: list[dict], stats: Counter) -> list[dict]:
    """Replace any token marked _split_shizukana with [静か, な] tokens."""
    out = []
    for tok in tokens:
        if tok.pop("_split_shizukana", False):
            # Build the split content token (静か, na_adjective). Carry over
            # word_id, is_new, etc. from the merged form.
            shizuka = dict(tok)
            shizuka["t"] = "静か"
            shizuka["r"] = "しずか"
            # Drop fields that don't belong on a non-merged token
            shizuka.pop("inflection", None)
            shizuka.pop("grammar_id", None)
            na = {"t": "な", "role": "particle", "grammar_id": "G016_na_adjective"}
            out.append(shizuka)
            out.append(na)
            stats[("apply_split_shizukana",)] += 1
        else:
            out.append(tok)
    return out


def normalize_story(story: dict, stats: Counter, warnings: list) -> bool:
    changed = False
    for sect in ("title", "subtitle"):
        toks = story.get(sect, {}).get("tokens", [])
        for tok in toks:
            if normalize_token(tok, stats, warnings):
                changed = True
        new_toks = _post_split_shizukana(toks, stats)
        if new_toks != toks:
            story[sect]["tokens"] = new_toks
            changed = True
    for sn in story.get("sentences", []):
        toks = sn.get("tokens", [])
        for tok in toks:
            if normalize_token(tok, stats, warnings):
                changed = True
        new_toks = _post_split_shizukana(toks, stats)
        if new_toks != toks:
            sn["tokens"] = new_toks
            changed = True

    # Story-level cleanup: drop G023_attributive from new_grammar (it was
    # collapsed into G022_i_adj) and replace with G022_i_adj if it isn't
    # already there.
    new_grammar = story.get("new_grammar") or []
    if isinstance(new_grammar, list) and "G023_attributive" in new_grammar:
        new_grammar.remove("G023_attributive")
        if "G022_i_adj" not in new_grammar:
            new_grammar.append("G022_i_adj")
        stats[("rewrite_new_grammar_g023",)] += 1
        changed = True

    # Note: we deliberately do NOT touch is_new_grammar markers — the
    # validator's notion of "first occurrence" is subtle (it accepts title,
    # subtitle, OR sentence depending on context) and rewriting them is
    # likely to introduce regressions. The G023→G022 collapse below could
    # leave a previously-tagged G023 first occurrence un-marked, but the
    # validator only requires *some* first occurrence carries the flag.

    return changed


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="Report changes only")
    g.add_argument("--apply",   action="store_true", help="Write changes (with backup)")
    ap.add_argument("--story", type=int, default=None, help="Process a single story_id")
    ap.add_argument("--stories-dir", default=str(ROOT / "stories"))
    args = ap.parse_args()

    if not JP_OK:
        print("WARN: fugashi not available; v3-slim re-derivation will be skipped.",
              file=sys.stderr)

    paths = sorted(Path(args.stories_dir).glob("story_*.json"),
                   key=lambda p: int(p.stem.split("_")[1]))
    if args.story is not None:
        paths = [p for p in paths if int(p.stem.split("_")[1]) == args.story]

    overall_stats: Counter = Counter()
    warnings: list[dict] = []
    changed_stories: list[int] = []

    for p in paths:
        sid = int(p.stem.split("_")[1])
        story = json.loads(p.read_text(encoding="utf-8"))
        story_stats: Counter = Counter()
        story_warnings: list[dict] = []
        if normalize_story(story, story_stats, story_warnings):
            changed_stories.append(sid)
            if args.apply:
                # Backup
                bak_dir = ROOT / "state_backups" / "normalize_to_v2"
                bak_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                shutil.copy(p, bak_dir / f"{p.stem}_{ts}.json")
                p.write_text(
                    json.dumps(story, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        for k, v in story_stats.items():
            overall_stats[k] += v
        for w in story_warnings:
            w["story_id"] = sid
            warnings.append(w)

    print("=" * 60)
    print(("APPLIED" if args.apply else "DRY-RUN") + f" — {len(paths)} stories scanned")
    print("=" * 60)
    print(f"Stories changed:   {len(changed_stories)}")
    if changed_stories:
        print(f"  IDs: {changed_stories[:20]}{' ...' if len(changed_stories) > 20 else ''}")
    print()
    print("Transformations applied:")
    for k, v in overall_stats.most_common():
        print(f"  {v:5d}  {k}")
    if warnings:
        print()
        print(f"Warnings ({len(warnings)}):")
        for w in warnings[:10]:
            print(f"  story {w['story_id']:3d}: {w}")
        if len(warnings) > 10:
            print(f"  ... and {len(warnings)-10} more")
    # Also clean up grammar_state.json: remove G023_attributive (it was
    # collapsed into G022_i_adj). Idempotent.
    if args.apply and args.story is None:
        gpath = ROOT / "data" / "grammar_state.json"
        if gpath.exists():
            gstate = json.loads(gpath.read_text(encoding="utf-8"))
            if "G023_attributive" in gstate.get("points", {}):
                # Backup
                bak_dir = ROOT / "state_backups" / "normalize_to_v2"
                bak_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                shutil.copy(gpath, bak_dir / f"grammar_state_{ts}.json")
                del gstate["points"]["G023_attributive"]
                gpath.write_text(
                    json.dumps(gstate, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                print()
                print("Removed G023_attributive from data/grammar_state.json")

    if args.apply and changed_stories:
        print()
        print(f"Backups written to state_backups/normalize_to_v2/")
        print("Recommended next steps:")
        print("  python3 -m pytest pipeline/tests/")
        print("  python3 pipeline/text_to_story_roundtrip.py --examples 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
