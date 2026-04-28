#!/usr/bin/env python3
"""The v2 author-loop orchestrator — the only sanctioned way to add a story.

Per `docs/phase3-tasks-2026-04-28.md` Task 1.11 + §B2.1 of the strategy doc.
The agent never edits `stories/*.json` directly; it writes a bilingual spec
to `pipeline/inputs/story_N.bilingual.json` and runs this orchestrator. The
orchestrator runs the full gauntlet:

    1. agent_brief         — assemble the JSON context the agent should
                              have consulted before writing the spec
    2. precheck            — fast preflight on the spec
    3. build               — deterministic tokenization (text_to_story)
    4. semantic_lint       — all 14 checks incl. v2 rules 11.7–11.10
    5. validate            — full library validator (Checks 1–11)
    5.5 mint_budget        — caps new vocab per story (skill §C defaults)
    5.6 pedagogical_sanity — every grammar point in `must_reinforce` debt
                              MUST appear in this story (mirrors the
                              test_pedagogical_sanity suite, pulled forward
                              into the gauntlet)
    6. literary_review     — STUB until Task 1.10 lands
    7. write to stories/   — only if every prior step passed
    8. audio rebuild       — STUB until wired to audio_builder

Steps 1–5.6 are HARD BLOCK per Phase 3 §0.1: a deterministic failure does
not ship the story. Step 6 is best-effort + warn (the literary review is
the single place where agentic judgment overrides; deterministic checks
do not).

Usage
-----
    author_loop.py author 11               # full gauntlet for story 11
    author_loop.py author 11 --dry-run     # don't write to stories/, just
                                           # report verdicts
    author_loop.py author 11 --brief-only  # just emit agent_brief JSON, exit
    author_loop.py author 11 --json        # machine-readable verdict report

Exit codes
----------
    0  — gauntlet passed (story shipped, or dry-run reported pass)
    1  — gauntlet failed at a hard-block step
    2  — usage / file-not-found error
    3  — gauntlet passed but literary-review escalated (story shipped with
         `reviewer_escalation: true` flag)
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any

# ── Make pipeline modules importable ─────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
PIPELINE = ROOT / "pipeline"
sys.path.insert(0, str(PIPELINE))
sys.path.insert(0, str(PIPELINE / "tools"))

from _paths import (  # noqa: E402
    INPUTS,
    STORIES,
    load_grammar,
    load_spec,
    load_vocab,
    parse_story_id,
    spec_path,
    story_path,
    write_json,
)
from text_to_story import build_story  # noqa: E402
from validate import validate as run_validate  # noqa: E402

# Tools
import agent_brief  # noqa: E402


# ── Step result containers ──────────────────────────────────────────────────

class StepResult:
    __slots__ = ("name", "status", "summary", "details", "blocking")

    def __init__(self, name: str, status: str, summary: str,
                 details: Any = None, blocking: bool = True):
        # status ∈ {"ok", "warn", "fail", "skipped"}
        self.name = name
        self.status = status
        self.summary = summary
        self.details = details
        self.blocking = blocking

    def to_dict(self) -> dict:
        return {
            "step": self.name,
            "status": self.status,
            "blocking": self.blocking,
            "summary": self.summary,
            "details": self.details,
        }


# ── Individual gauntlet steps ───────────────────────────────────────────────

def step_agent_brief(story_id: int) -> StepResult:
    try:
        brief = agent_brief.build_brief(story_id)
        return StepResult(
            "agent_brief", "ok",
            f"Brief assembled: {brief['palette']['summary']['total_available_words']} "
            f"words available, {len(brief['grammar_points'])} grammar points, "
            f"{brief['reinforcement_debt']['critical'].__len__()} critical-debt words.",
            details=None,  # don't dump the full brief into the verdict
        )
    except Exception as e:
        return StepResult(
            "agent_brief", "fail",
            f"agent_brief crashed: {e}",
            details=traceback.format_exc(),
        )


def step_spec_exists(story_id: int) -> StepResult:
    sp = spec_path(story_id)
    if not sp.exists():
        return StepResult(
            "spec_exists", "fail",
            f"No spec at {sp}. The agent must write the bilingual spec "
            f"before running the gauntlet.",
        )
    try:
        spec = load_spec(story_id)
    except Exception as e:
        return StepResult("spec_exists", "fail",
                          f"Spec at {sp} is not valid JSON: {e}")
    sentences = spec.get("sentences") or []
    return StepResult(
        "spec_exists", "ok",
        f"Spec found at {sp.name} with {len(sentences)} sentences.",
    )


def step_build(story_id: int) -> tuple[StepResult, dict | None, dict | None]:
    """Run text_to_story. Returns (StepResult, built_story, build_report)."""
    try:
        spec = load_spec(story_id)
        vocab = load_vocab()
        grammar = load_grammar()
        built, report = build_story(spec, vocab, grammar)
        new_words = list((report or {}).get("new_words") or [])
        unresolved = list((report or {}).get("unresolved") or [])
        if unresolved:
            return (StepResult(
                "build", "fail",
                f"Build produced {len(unresolved)} unresolved tokens: "
                f"{unresolved[:5]}...",
                details=unresolved,
            ), None, None)
        return (StepResult(
            "build", "ok",
            f"Built clean. {len(new_words)} new word mints: {new_words}.",
            details={"new_words": new_words},
        ), built, report)
    except Exception as e:
        return (StepResult(
            "build", "fail",
            f"text_to_story crashed: {e}",
            details=traceback.format_exc(),
        ), None, None)


def step_validate(built_story: dict, build_report: dict | None = None) -> StepResult:
    """Run the full validator (Checks 1–11) including the v2 lints."""
    try:
        vocab = load_vocab()
        grammar = load_grammar()
        # Build a minimal plan from the build report so Check 2 allows freshly-
        # minted words and Check 3 allows freshly-introduced grammar points.
        # `unknown_grammar` is the build report's catch-all for any tagger-
        # emitted grammar_id that isn't yet in grammar_state.json — most
        # importantly the auto-tagged paradigm anchors registered in
        # `text_to_story.KNOWN_AUTO_GRAMMAR_DEFINITIONS` (e.g. G055 for the
        # first plain-form verb usage). Without splicing those into
        # plan["new_grammar"], validator Check 3 ("grammar_id 'G055_…' not
        # in grammar_state or plan") would block a story that the rest of
        # the gauntlet considers clean.
        plan: dict | None = None
        if build_report:
            minted_word_ids = [w["id"] for w in (build_report.get("new_words") or [])]
            minted_grammar  = list(build_report.get("new_grammar") or [])
            for rec in (build_report.get("unknown_grammar") or []):
                if isinstance(rec, dict):
                    g = rec.get("grammar_id")
                    if g and g not in minted_grammar:
                        minted_grammar.append(g)
            plan = {
                "new_words": minted_word_ids,
                "new_grammar": minted_grammar,
            }
            # Check 4 compares story["new_words"] against plan["new_words"] AND
            # requires is_new: true on first-occurrence tokens. Both are normally
            # stamped by regenerate_all_stories *after* shipping. Pre-populate
            # them here so the gauntlet validator sees a consistent picture.
            import copy as _copy
            built_story = _copy.deepcopy(built_story)  # don't mutate caller's copy
            if not built_story.get("new_words"):
                built_story["new_words"] = minted_word_ids
            # Stamp is_new: true on the first occurrence of each minted word.
            minted_set = set(minted_word_ids)
            seen: set[str] = set()
            all_sections: list[tuple[str, list[dict]]] = []
            title_tokens = built_story.get("title_tokens") or []
            if title_tokens:
                all_sections.append(("title", title_tokens))
            for s in built_story.get("sentences", []):
                all_sections.append(("sentence", s.get("tokens", [])))
            for _sec, tokens in all_sections:
                for tok in tokens:
                    wid = tok.get("word_id")
                    if wid and wid in minted_set and wid not in seen:
                        tok["is_new"] = True
                        seen.add(wid)
        result = run_validate(built_story, vocab, grammar, plan=plan)
        if result.valid:
            warn_count = len(result.warnings) if hasattr(result, "warnings") else 0
            return StepResult(
                "validate", "ok",
                f"Validator passed (Checks 1–11). {warn_count} warning(s).",
            )
        # group errors by check id
        by_check: dict[str, list[str]] = {}
        for err in result.errors:
            by_check.setdefault(str(err.check), []).append(
                f"[{err.location or '-'}] {err.message}"
            )
        return StepResult(
            "validate", "fail",
            f"Validator reported {len(result.errors)} error(s) across "
            f"{len(by_check)} check(s).",
            details=by_check,
        )
    except Exception as e:
        return StepResult(
            "validate", "fail",
            f"validate() crashed: {e}",
            details=traceback.format_exc(),
        )


def _apply_post_pass_attributions(built_story: dict) -> None:
    """Apply the subset of `regenerate_all_stories.regen_one` post-passes
    whose absence would cause the gauntlet's pedagogical_sanity check to
    produce false-positive failures (i.e. flagging a grammar point as
    missing when the post-ship file would actually carry it).

    This duplicates a fragment of regenerate_all_stories.py's logic. The
    correct long-term refactor is to factor that post-pass into a shared
    helper module, but for v2 phase 3a the duplicated subset is small and
    the failure mode of NOT having it is actively misleading.

    Mutates `built_story` in place.
    """
    NAN_SURFACES = {"何", "なに", "なん"}
    KOSOADO_SURFACES = {"あの", "この", "その", "どの"}
    INTERROGATIVE_GIDS = {
        "だれ": "G039_dare_who", "誰":   "G039_dare_who",
        "どこ": "G040_doko_where",
        "いつ": "G042_itsu_when",
        "なぜ": "G053_naze_why",
    }
    COUNTER_SURFACES = {"一人", "二人", "三人", "四人", "五人", "ひとり", "ふたり"}
    ARU_IRU_BASES   = {"ある", "いる"}
    QUOTATIVE_VERBS = {
        "思います": "G014_to_omoimasu",
        "言います": "G028_to_iimasu",
    }

    for sent in built_story.get("sentences", []):
        toks = sent.get("tokens", [])
        # Pass A: surface/base-driven retags
        for tok in toks:
            t = tok.get("t", "")
            if t in NAN_SURFACES:
                tok["grammar_id"] = "G045_nan_what"
            elif t in KOSOADO_SURFACES and tok.get("role") == "content":
                tok["grammar_id"] = "G043_kosoado_pre_nominal"
            elif t in INTERROGATIVE_GIDS:
                tok["grammar_id"] = INTERROGATIVE_GIDS[t]
            elif t in COUNTER_SURFACES and tok.get("role") == "content":
                tok["grammar_id"] = "G025_counters"
            elif tok.get("role") == "content":
                base = (tok.get("inflection") or {}).get("base")
                cur_gid = tok.get("grammar_id")
                if base in ARU_IRU_BASES and cur_gid in (None, "G026_masu_nonpast"):
                    tok["grammar_id"] = "G021_aru_iru"
        # Pass B: quotative と + 思います/言います
        for j in range(len(toks) - 1, -1, -1):
            qv = toks[j].get("t")
            if qv in QUOTATIVE_VERBS:
                quot_gid = QUOTATIVE_VERBS[qv]
                for k in range(j - 1, -1, -1):
                    if toks[k].get("t") == "と" and toks[k].get("role") == "particle":
                        toks[k]["grammar_id"] = quot_gid
                        toks[j]["role"] = "aux"
                        break


def step_pedagogical_sanity(story_id: int, built_story: dict) -> StepResult:
    """Hard-block step: would shipping this story break grammar reinforcement?

    Pulls `grammar_reinforcement_debt` from the brief. For every entry with
    `must_reinforce: true`, the built story MUST contain a token whose
    `grammar_id` (or `inflection.grammar_id`) matches. Missing reinforcement
    used to silently slip past validate() and only surface in pytest after
    shipping; this step pulls that detection forward into the gauntlet.

    Also reports `should_reinforce` items as warnings (non-blocking, to
    let the agent know the next story will need to carry them).
    """
    try:
        brief = agent_brief.build_brief(story_id)
        debt = brief.get("grammar_reinforcement_debt") or {}
        items = debt.get("items") or []
        if not items:
            return StepResult(
                "pedagogical_sanity", "ok",
                "No grammar reinforcement debt to satisfy.",
            )

        # Collect every grammar_id used in the would-build story.
        # IMPORTANT: text_to_story.build_story emits per-token grammar_ids,
        # but several context-sensitive points are attached only by the
        # `regenerate_all_stories.regen_one` post-pass (e.g. G021_aru_iru,
        # G014_to_omoimasu, G028_to_iimasu, G030_kara_reason, etc.). The
        # gauntlet runs before regenerate, so we re-apply the subset of
        # post-passes whose absence would cause false-positive failures
        # against the pedagogical-sanity test.
        _apply_post_pass_attributions(built_story)
        used: set[str] = set()
        for sent in built_story.get("sentences", []):
            for tok in sent.get("tokens", []):
                for gid in (tok.get("grammar_id"),
                            (tok.get("inflection") or {}).get("grammar_id")):
                    if gid:
                        used.add(gid)

        missing_must: list[dict] = []
        carried_must: list[str] = []
        missing_should: list[dict] = []
        carried_should: list[str] = []
        for item in items:
            gid = item["grammar_id"]
            if item.get("must_reinforce"):
                if gid in used:
                    carried_must.append(gid)
                else:
                    missing_must.append(item)
            elif item.get("should_reinforce"):
                if gid in used:
                    carried_should.append(gid)
                else:
                    missing_should.append(item)

        if missing_must:
            lines = []
            for it in missing_must:
                ex = it.get("example") or {}
                # Why is this a MUST? Either the window is closing on this
                # story, or there are no shipped follow-ups yet (so this is
                # the only currently-shipping chance).
                if story_id == it["window_end"]:
                    why = f"window closes at this story (intro'd in story {it['intro_in_story']}, +{it['window_end'] - it['intro_in_story']} window)"
                else:
                    why = (
                        f"intro'd in story {it['intro_in_story']}; no shipped "
                        f"follow-up has reinforced it yet, so this story is "
                        f"the next chance and must carry it"
                    )
                lines.append(
                    f"  - {it['grammar_id']} ({it.get('label','')}): {why}. "
                    f"Sample construction: 「{ex.get('surface','')}」"
                )
            return StepResult(
                "pedagogical_sanity", "fail",
                f"Story {story_id} is the LAST chance to reinforce "
                f"{len(missing_must)} grammar point(s); the built story "
                f"does not use them. Add at least one sentence per point.",
                details={
                    "must_reinforce_missing": [it["grammar_id"] for it in missing_must],
                    "must_reinforce_satisfied": carried_must,
                    "should_reinforce_missing": [it["grammar_id"] for it in missing_should],
                    "explanation": "\n".join(lines),
                },
            )

        # All musts satisfied; report shoulds as info.
        status = "warn" if missing_should else "ok"
        summary = (
            f"All {len(carried_must)} must-reinforce point(s) carried."
            if carried_must
            else "No must-reinforce points required."
        )
        if missing_should:
            summary += (
                f" {len(missing_should)} should-reinforce point(s) deferred "
                f"to a later story (within window): "
                f"{', '.join(it['grammar_id'] for it in missing_should)}."
            )
        return StepResult(
            "pedagogical_sanity", status, summary,
            details={
                "must_reinforce_satisfied": carried_must,
                "should_reinforce_satisfied": carried_should,
                "should_reinforce_deferred": [it["grammar_id"] for it in missing_should],
            },
            blocking=False,  # warn-level shoulds never block
        )
    except Exception as e:
        return StepResult(
            "pedagogical_sanity", "fail",
            f"pedagogical_sanity crashed: {e}",
            details=traceback.format_exc(),
        )


def step_vocab_reinforcement(story_id: int, built_story: dict) -> StepResult:
    """Hard-block step: would shipping break per-word reinforcement (R1)?

    For every entry in `vocab_reinforcement_debt` flagged
    `must_reinforce: true`, the built story MUST contain a token whose
    `word_id` matches. Same shape as step_pedagogical_sanity but for
    vocab. Catches the failure mode that bit story 8 (where 箱 and 紙
    were intro'd in story 7 but never showed up in the brief's
    `word_reinforcement.critical/due` because the palette-star path
    only kicks in after 8 stories of unused).
    """
    try:
        brief = agent_brief.build_brief(story_id)
        debt = brief.get("vocab_reinforcement_debt") or {}
        items = debt.get("items") or []
        if not items:
            return StepResult(
                "vocab_reinforcement", "ok",
                "No vocab reinforcement debt to satisfy.",
            )

        used: set[str] = set()
        for sec in (built_story.get("title") or {},):
            for tok in sec.get("tokens", []) or []:
                if tok.get("word_id"):
                    used.add(tok["word_id"])
        for sent in built_story.get("sentences", []):
            for tok in sent.get("tokens", []):
                if tok.get("word_id"):
                    used.add(tok["word_id"])

        missing_must: list[dict] = []
        carried_must: list[str] = []
        missing_should: list[dict] = []
        carried_should: list[str] = []
        for item in items:
            wid = item["word_id"]
            if item.get("must_reinforce"):
                if wid in used:
                    carried_must.append(wid)
                else:
                    missing_must.append(item)
            elif item.get("should_reinforce"):
                if wid in used:
                    carried_should.append(wid)
                else:
                    missing_should.append(item)

        if missing_must:
            lines = []
            for it in missing_must:
                lines.append(
                    f"  - {it['word_id']} ({it['lemma']}): intro'd in story "
                    f"{it['intro_in_story']}, no shipped follow-up has reused "
                    f"it; this story must carry it (R1 window {debt.get('window')})."
                )
            return StepResult(
                "vocab_reinforcement", "fail",
                f"Story {story_id} must reuse {len(missing_must)} word(s) "
                f"intro'd in the immediately previous story; "
                f"the built story does not. Add a sentence using each.",
                details={
                    "must_reinforce_missing":   [it["word_id"] for it in missing_must],
                    "must_reinforce_satisfied": carried_must,
                    "should_reinforce_missing": [it["word_id"] for it in missing_should],
                    "explanation":              "\n".join(lines),
                },
            )

        status = "warn" if missing_should else "ok"
        summary = (
            f"All {len(carried_must)} must-reinforce word(s) carried."
            if carried_must
            else "No must-reinforce words required."
        )
        if missing_should:
            summary += (
                f" {len(missing_should)} should-reinforce word(s) deferred "
                f"to a later story (within window): "
                f"{', '.join(it['word_id'] for it in missing_should[:5])}"
                f"{'…' if len(missing_should) > 5 else ''}."
            )
        return StepResult(
            "vocab_reinforcement", status, summary,
            details={
                "must_reinforce_satisfied":   carried_must,
                "should_reinforce_satisfied": carried_should,
                "should_reinforce_deferred":  [it["word_id"] for it in missing_should],
            },
            blocking=False,
        )
    except Exception as e:
        return StepResult(
            "vocab_reinforcement", "fail",
            f"vocab_reinforcement crashed: {e}",
            details=traceback.format_exc(),
        )


def step_coverage_floor(story_id: int, built_story: dict) -> StepResult:
    """Hard-block step: does this story introduce ≥1 new grammar point
    while the current tier still has uncovered catalog entries?

    Mirrors validator's Check 3.10 but reports earlier in the gauntlet
    with a concrete pick list pulled from the brief's
    `grammar_introduction_debt.recommended_for_this_story`. Skipped during
    the bootstrap window (stories 1..BOOTSTRAP_END) since the bootstrap is
    policed in aggregate, not per-story.
    """
    try:
        from grammar_progression import BOOTSTRAP_END  # noqa: E402
    except Exception:
        BOOTSTRAP_END = 3
    if story_id <= BOOTSTRAP_END:
        return StepResult(
            "coverage_floor", "skipped",
            f"Bootstrap window (stories 1..{BOOTSTRAP_END}) — per-story "
            f"floor doesn't apply.",
            blocking=False,
        )
    try:
        brief = agent_brief.build_brief(story_id)
        debt = brief.get("grammar_introduction_debt") or {}
        if not debt.get("must_introduce"):
            return StepResult(
                "coverage_floor", "ok",
                f"All tiers ≤ {debt.get('current_jlpt','?')} are fully "
                f"covered; no introduction required.",
                details={"coverage_summary": debt.get("coverage_summary")},
            )
        # Walk the built story's `new_grammar` array.
        story_intros = built_story.get("new_grammar") or []
        # text_to_story leaves new_grammar empty until the post-pass; the
        # first-occurrence flagger runs in regenerate_all_stories, not here.
        # As a fallback, inspect tokens directly for grammar_ids that are
        # not yet in grammar_state with intro_in_story != None.
        if not story_intros:
            try:
                from grammar_progression import coverage_status as _cov
                covered_cids = set(_cov()["covered_catalog_ids"].keys())
                # Map gid → catalog_id. Two sources, in priority order:
                #   1. grammar_state.json — the canonical store. Most gids
                #      live here, even those not yet attributed (their
                #      `intro_in_story` is None until the first usage).
                #   2. KNOWN_AUTO_GRAMMAR_DEFINITIONS — the in-code
                #      registry for auto-tagged paradigm anchors that
                #      have never been bulk-loaded into state (e.g.
                #      G055_plain_nonpast_pair, the first plain-form
                #      verb usage in the corpus). Without this fallback,
                #      a gid the tagger emits but state doesn't know
                #      yet would map to None and the intro would not
                #      be counted — the same defect Check 3.10 had
                #      before the registry was introduced.
                from text_to_story import (  # noqa: E402
                    KNOWN_AUTO_GRAMMAR_DEFINITIONS as _AUTO_DEFS,
                )
                import json as _json
                from _paths import DATA as _DATA
                gstate = _json.loads((_DATA / "grammar_state.json").read_text())
                gid_to_cid = {
                    gid: e.get("catalog_id")
                    for gid, e in (gstate.get("points") or {}).items()
                }
                # Registry entries take effect ONLY when the gid is not
                # already in state (state is the source of truth once
                # ship attribution has happened).
                for gid, defn in _AUTO_DEFS.items():
                    if gid not in gid_to_cid and defn.get("catalog_id"):
                        gid_to_cid[gid] = defn["catalog_id"]
                used_gids: set[str] = set()
                for sent in built_story.get("sentences", []):
                    for tok in sent.get("tokens", []):
                        for g in (tok.get("grammar_id"),
                                  (tok.get("inflection") or {}).get("grammar_id")):
                            if g:
                                used_gids.add(g)
                story_intros = [
                    g for g in used_gids
                    if (cid := gid_to_cid.get(g)) and cid not in covered_cids
                ]
            except Exception:
                pass

        if story_intros:
            return StepResult(
                "coverage_floor", "ok",
                f"Story introduces {len(story_intros)} new grammar point(s): "
                f"{sorted(story_intros)}.",
                details={"intros": sorted(story_intros)},
            )
        # Fail — build a clear pick list.
        recs = debt.get("recommended_for_this_story") or []
        rec_lines = [
            f"  - {r['catalog_id']} ({r.get('jlpt')}): {r.get('title','')}"
            f" — {r.get('short','')}"
            for r in recs
        ] or ["  (no prereq-ready picks; check earlier_uncovered first)"]
        return StepResult(
            "coverage_floor", "fail",
            f"Story {story_id} introduces 0 new grammar points but the "
            f"current tier ({debt.get('current_jlpt','?')}) still has "
            f"{sum(b['remaining'] for b in (debt.get('coverage_summary') or {}).values())} "
            f"uncovered point(s). Pick at least one from "
            f"`grammar_introduction_debt.recommended_for_this_story`.",
            details={
                "coverage_summary": debt.get("coverage_summary"),
                "recommended": recs,
                "recommendations_human": "\n".join(rec_lines),
            },
        )
    except Exception as e:
        return StepResult(
            "coverage_floor", "fail",
            f"coverage_floor crashed: {e}",
            details=traceback.format_exc(),
        )


def step_mint_budget(story_id: int, build_report: dict | None) -> StepResult:
    """Soft-block check: did this story respect its mint_budget?

    Per the monogatari-author skill: mint discipline is the agent's
    responsibility but the gauntlet should at least surface a clear
    error when the cap is breached so the user notices instead of
    silently absorbing curriculum drift.
    """
    try:
        brief = agent_brief.build_brief(story_id)
        budget = brief.get("mint_budget") or {}
        cap = int(budget.get("max", 9999))
        new_words = list((build_report or {}).get("new_words") or [])
        n_minted = len(new_words)
        if n_minted <= cap:
            return StepResult(
                "mint_budget", "ok",
                f"Minted {n_minted} new word(s); within cap of {cap}.",
                details={"minted": [w.get("id") for w in new_words], "cap": cap},
            )
        return StepResult(
            "mint_budget", "fail",
            f"Minted {n_minted} new word(s) but cap is {cap}. "
            f"Trim mints or document the expansion in the spec's `intent`.",
            details={
                "minted": [w.get("id") for w in new_words],
                "cap": cap,
                "rationale": budget.get("rationale", ""),
            },
        )
    except Exception as e:
        return StepResult(
            "mint_budget", "fail",
            f"mint_budget crashed: {e}",
            details=traceback.format_exc(),
        )


def step_literary_review(built_story: dict) -> StepResult:
    """STUB until Task 1.10 (`pipeline/literary_review.py`) lands.

    Per Phase 3 §0.1, the literary reviewer is the ONE non-blocking step:
    failures cause the story to ship with `reviewer_escalation: true`,
    not to halt the pipeline.
    """
    return StepResult(
        "literary_review", "skipped",
        "Stub: pipeline/literary_review.py is not yet implemented "
        "(Phase 3a Task 1.10). Story ships without literary review for now.",
        blocking=False,
    )


def step_audio(story_id: int, dry_run: bool) -> StepResult:
    """Build per-sentence and per-word MP3s via Google TTS.

    Skipped on --dry-run. The audio_builder is incremental — re-running
    is cheap; it skips files that exist with a matching content hash.
    Audio is part of the shipping contract (per skill §F.1), so any
    failure here is a hard fail at ship time.
    """
    if dry_run:
        return StepResult(
            "audio", "skipped",
            "--dry-run: skipping audio build.",
            blocking=False,
        )
    try:
        from audio_builder import build_audio_for_story  # noqa: E402
        sp = story_path(story_id)
        if not sp.exists():
            return StepResult(
                "audio", "skipped",
                f"Story file {sp.name} not found (write step skipped or failed).",
                blocking=False,
            )
        from _paths import DATA as _DATA
        vocab = json.loads((_DATA / "vocab_state.json").read_text(encoding="utf-8"))
        summary = build_audio_for_story(sp, vocab, audio_root=ROOT / "audio")
        return StepResult(
            "audio", "ok",
            f"Audio built: {summary['sentences']} sentence(s), "
            f"{summary['words']} word(s) → {summary['out_dir']}.",
            details=summary,
        )
    except Exception as e:
        return StepResult(
            "audio", "fail",
            f"audio build failed: {e}",
            details=traceback.format_exc(),
        )


def _build_state_plan(build_report: dict | None) -> dict:
    """Convert text_to_story's mint records into a state_updater plan.

    text_to_story.build_story emits `report["new_words"]` with full
    metadata (surface, kana, reading, pos, meanings, verb_class, adj_class,
    `_minted_by`). state_updater wants
    `plan["new_word_definitions"][wid]` with surface/kana/reading/pos/
    meanings/verb_class/adj_class. Building the plan from the report
    eliminates the entire hand-written sidecar JSON step that bit story 8.

    Auto-tagged grammar gids that are NOT yet in grammar_state.json
    (e.g. G055_plain_nonpast_pair on the first plain-form verb usage)
    are surfaced via the build report's `unknown_grammar` list. For each
    such gid that has a registered definition in
    `text_to_story.KNOWN_AUTO_GRAMMAR_DEFINITIONS`, we splice the
    definition into the plan so state_updater can attribute the new
    point cleanly. Without this hop, the first plain-form verb in the
    corpus would crash state_updater with "Cannot ship: new_grammar
    'G055_…' has no complete definition in plan."
    """
    plan: dict = {"new_word_definitions": {}, "new_grammar_definitions": {}}
    if not build_report:
        return plan
    for rec in build_report.get("new_words", []) or []:
        wid = rec.get("id")
        if not wid:
            continue
        defn: dict = {
            "surface":  rec.get("surface", wid),
            "kana":     rec.get("kana", ""),
            "reading":  rec.get("reading", ""),
            "pos":      rec.get("pos", "noun"),
            "meanings": list(rec.get("meanings") or []),
        }
        if rec.get("verb_class"):
            defn["verb_class"] = rec["verb_class"]
        if rec.get("adj_class"):
            defn["adj_class"] = rec["adj_class"]
        plan["new_word_definitions"][wid] = defn

    # Splice in any auto-tagged grammar definitions that the builder
    # surfaced as unknown to state. We deduplicate by gid because the
    # same gid may appear on multiple tokens within a single story (a
    # verb in dict form on s2 and on s5, say).
    from text_to_story import KNOWN_AUTO_GRAMMAR_DEFINITIONS  # noqa: E402
    seen_gids: set[str] = set()
    for rec in build_report.get("unknown_grammar", []) or []:
        gid = rec.get("grammar_id") if isinstance(rec, dict) else None
        if not gid or gid in seen_gids:
            continue
        seen_gids.add(gid)
        defn = KNOWN_AUTO_GRAMMAR_DEFINITIONS.get(gid)
        if defn:
            # Copy so callers can't mutate the registry by accident.
            plan["new_grammar_definitions"][gid] = dict(defn)

    return plan


def step_write(story_id: int, built_story: dict,
               build_report: dict | None, dry_run: bool) -> StepResult:
    """Write the built story AND update vocab/grammar state AND set is_new flags.

    On --dry-run: no-op (skipped, non-blocking).

    On live ship, runs the full post-ship state chain in one shot:
      1. write stories/story_N.json
      2. state_updater(plan from build_report) — mints new W-IDs and
         attributes new grammar points.
      3. regenerate_all_stories(--story N) — rewrites is_new / is_new_grammar
         flags now that state is final.

    This collapses the four-command dance documented in AGENTS.md
    ("regenerate → state_updater(--plan) → regenerate") into a single
    author_loop invocation. Hand-built plan files are no longer required.
    """
    if dry_run:
        return StepResult(
            "write", "skipped",
            f"--dry-run: would have written {story_path(story_id).name} "
            "and persisted vocab/grammar state.",
            blocking=False,
        )
    try:
        sp = story_path(story_id)
        write_json(sp, built_story)
    except Exception as e:
        return StepResult("write", "fail",
                          f"Could not write story file: {e}",
                          details=traceback.format_exc())

    # The chain order is: regenerate → state_updater → regenerate.
    # The first regenerate populates the story file's `new_words` and
    # `new_grammar` arrays by walking the corpus to find first-occurrence
    # word_ids; without those arrays, state_updater sees nothing to
    # add and silently mints zero records (the bug that bit story 8 in
    # the 2026-04-28 session, twice). The second regenerate refreshes
    # `is_new` flags now that vocab/grammar state is final. Both
    # invocations are shelled out because regenerate_all_stories has
    # corpus-wide side effects (index.json, paged caches) wrapped in
    # its argparse main().
    import subprocess

    def _regen_one() -> StepResult | None:
        result = subprocess.run(
            [sys.executable, str(PIPELINE / "regenerate_all_stories.py"),
             "--story", str(story_id), "--apply"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        if result.returncode != 0:
            return StepResult(
                "write", "fail",
                f"regenerate_all_stories failed: {result.stderr.strip()}",
                details={"stdout": result.stdout, "stderr": result.stderr},
            )
        return None

    # --- Regenerate #1: populate new_words / new_grammar arrays ---------
    try:
        err = _regen_one()
        if err is not None:
            return err
    except Exception as e:
        return StepResult(
            "write", "fail",
            f"regenerate_all_stories crashed (first pass): {e}",
            details=traceback.format_exc(),
        )

    # --- State update: mint vocab + attribute grammar -------------------
    try:
        from state_updater import update_state  # noqa: E402
        from _paths import DATA as _DATA
        vocab_path   = _DATA / "vocab_state.json"
        grammar_path = _DATA / "grammar_state.json"

        vocab   = json.loads(vocab_path.read_text(encoding="utf-8"))
        grammar = json.loads(grammar_path.read_text(encoding="utf-8"))
        # Re-read the just-regenerated story so state_updater sees the
        # new_words / new_grammar arrays the regenerator populated.
        story_for_state = json.loads(sp.read_text(encoding="utf-8"))
        plan = _build_state_plan(build_report)

        new_vocab, new_grammar, summary = update_state(
            story_for_state, vocab, grammar, plan,
        )
        # Backups (mirrors state_updater.main behavior).
        from state_updater import backup as _backup
        _backup(vocab_path)
        _backup(grammar_path)
        write_json(vocab_path,   new_vocab)
        write_json(grammar_path, new_grammar)
    except Exception as e:
        return StepResult(
            "write", "fail",
            f"state_updater failed after regenerate: {e}",
            details=traceback.format_exc(),
        )

    # --- Regenerate #2: rewrite is_new flags under final word_ids -------
    try:
        err = _regen_one()
        if err is not None:
            return err
    except Exception as e:
        return StepResult(
            "write", "fail",
            f"regenerate_all_stories crashed (second pass): {e}",
            details=traceback.format_exc(),
        )

    return StepResult(
        "write", "ok",
        f"Wrote {sp.name}, updated vocab/grammar state "
        f"({len(summary.get('words_added') or [])} new word(s), "
        f"{len(summary.get('grammar_added') or [])} new grammar point(s)), "
        f"and refreshed is_new flags.",
        details={
            "words_added":   summary.get("words_added"),
            "grammar_added": summary.get("grammar_added"),
        },
    )


# ── The orchestrator ────────────────────────────────────────────────────────

def run_gauntlet(story_id: int, *, dry_run: bool) -> dict:
    """Run the gauntlet end to end. Returns a structured verdict dict.

    Hard-block steps fail-fast: as soon as a blocking step fails, the
    remaining blocking steps are skipped (with status "skipped") and the
    story is NOT written.
    """
    steps: list[StepResult] = []

    # Step 0.5: spec exists & loadable
    s_spec = step_spec_exists(story_id)
    steps.append(s_spec)
    if s_spec.status == "fail":
        return _make_verdict(story_id, steps, dry_run, halted_at="spec_exists")

    # Step 1: brief (informational; don't halt on its failure since the
    # spec is already written)
    steps.append(step_agent_brief(story_id))

    # Step 3: build
    s_build, built, report = step_build(story_id)
    steps.append(s_build)
    if s_build.status == "fail":
        return _make_verdict(story_id, steps, dry_run, halted_at="build")

    # Step 4-5: validate (covers semantic_lint via Check 11)
    s_val = step_validate(built, build_report=report)
    steps.append(s_val)
    if s_val.status == "fail":
        return _make_verdict(story_id, steps, dry_run, halted_at="validate")

    # Step 5.5: mint budget (HARD BLOCK — keeps the corpus from silent
    # vocab drift when the agent over-mints).
    s_mint = step_mint_budget(story_id, report)
    steps.append(s_mint)
    if s_mint.status == "fail":
        return _make_verdict(story_id, steps, dry_run, halted_at="mint_budget")

    # Step 5.6: pedagogical sanity (HARD BLOCK on must-reinforce; warn on
    # should-reinforce). Catches grammar reinforcement debt BEFORE shipping
    # so the test suite never goes red after an author_loop "ship".
    s_ped = step_pedagogical_sanity(story_id, built)
    steps.append(s_ped)
    if s_ped.status == "fail":
        return _make_verdict(story_id, steps, dry_run, halted_at="pedagogical_sanity")

    # Step 5.65: vocab reinforcement (HARD BLOCK on must-reinforce). Catches
    # the test_vocab_words_are_reinforced (R1) failure that bit story 8 —
    # words intro'd in story N-1 must reappear in story N.
    s_vocab = step_vocab_reinforcement(story_id, built)
    steps.append(s_vocab)
    if s_vocab.status == "fail":
        return _make_verdict(story_id, steps, dry_run, halted_at="vocab_reinforcement")

    # Step 5.7: coverage floor (HARD BLOCK). Every post-bootstrap story
    # must introduce ≥1 new grammar point until the current JLPT tier
    # is fully covered. Mirrors validator's Check 3.10 with a clearer
    # pick list pulled from the brief.
    s_cov = step_coverage_floor(story_id, built)
    steps.append(s_cov)
    if s_cov.status == "fail":
        return _make_verdict(story_id, steps, dry_run, halted_at="coverage_floor")

    # Step 6: literary review (non-blocking)
    s_rev = step_literary_review(built)
    steps.append(s_rev)

    # Step 7: write (also persists vocab/grammar state and refreshes
    # is_new flags on a live ship — see step_write docstring).
    s_write = step_write(story_id, built, report, dry_run)
    steps.append(s_write)
    if s_write.status == "fail":
        return _make_verdict(story_id, steps, dry_run, halted_at="write")

    # Step 8: audio (skipped on --dry-run; hard-fails the ship if it
    # crashes since audio is part of the shipping contract).
    s_audio = step_audio(story_id, dry_run)
    steps.append(s_audio)
    if s_audio.status == "fail":
        return _make_verdict(story_id, steps, dry_run, halted_at="audio")

    return _make_verdict(story_id, steps, dry_run)


def _make_verdict(story_id: int, steps: list[StepResult],
                  dry_run: bool, halted_at: str | None = None) -> dict:
    blocking_failures = [s for s in steps if s.blocking and s.status == "fail"]
    reviewer_escalated = any(
        s.name == "literary_review" and s.status == "warn" for s in steps
    )
    if blocking_failures:
        verdict = "fail"
        exit_code = 1
    elif reviewer_escalated:
        verdict = "ship_with_warning"
        exit_code = 3
    else:
        verdict = "ship" if not dry_run else "would_ship"
        exit_code = 0
    return {
        "story_id": story_id,
        "verdict": verdict,
        "exit_code": exit_code,
        "halted_at": halted_at,
        "dry_run": dry_run,
        "steps": [s.to_dict() for s in steps],
    }


# ── CLI ─────────────────────────────────────────────────────────────────────

def _format_human(verdict: dict) -> str:
    lines = [f"\nGAUNTLET — story {verdict['story_id']}  "
             f"({'DRY RUN' if verdict['dry_run'] else 'LIVE'})"]
    lines.append("─" * 70)
    icons = {"ok": "✓", "warn": "!", "fail": "✗", "skipped": "·"}
    for s in verdict["steps"]:
        icon = icons.get(s["status"], "?")
        block = "" if s["blocking"] else "  (non-blocking)"
        lines.append(f"  {icon} {s['step']:<18s} {s['summary']}{block}")
        if s["status"] == "fail" and s.get("details"):
            d = s["details"]
            if isinstance(d, dict):
                for check_id, msgs in d.items():
                    lines.append(f"      {check_id}:")
                    if isinstance(msgs, str):
                        for line in msgs.splitlines()[:10]:
                            lines.append(f"        {line}")
                        continue
                    if not isinstance(msgs, (list, tuple)):
                        lines.append(f"        {msgs}")
                        continue
                    for m in msgs[:6]:
                        lines.append(f"        {m}")
                    if len(msgs) > 6:
                        lines.append(f"        ... +{len(msgs) - 6} more")
            else:
                detail_str = str(d)
                for line in detail_str.splitlines()[:10]:
                    lines.append(f"      {line}")
    lines.append("─" * 70)
    lines.append(f"VERDICT: {verdict['verdict']}  (exit {verdict['exit_code']})")
    if verdict.get("halted_at"):
        lines.append(f"halted at: {verdict['halted_at']}")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("author", help="run the gauntlet on a story id")
    a.add_argument("story", help="story id, 'story_N', or path to spec")
    a.add_argument("--dry-run", action="store_true",
                   help="don't write to stories/; just report")
    a.add_argument("--brief-only", action="store_true",
                   help="emit compact author brief JSON for this story id and exit")
    a.add_argument("--full-brief", action="store_true",
                   help="with --brief-only, emit the complete tooling brief")
    a.add_argument("--json", action="store_true",
                   help="emit verdict as JSON instead of human format")
    args = p.parse_args()

    story_id = parse_story_id(args.story)

    if args.brief_only:
        brief = (agent_brief.build_brief(story_id)
                 if args.full_brief
                 else agent_brief.build_author_brief(story_id))
        print(json.dumps(brief, ensure_ascii=False, indent=2))
        sys.exit(0)

    verdict = run_gauntlet(story_id, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(verdict, ensure_ascii=False, indent=2))
    else:
        print(_format_human(verdict))
    sys.exit(verdict["exit_code"])


if __name__ == "__main__":
    main()
