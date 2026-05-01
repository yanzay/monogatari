#!/usr/bin/env python3
"""The v2 author-loop orchestrator — the only sanctioned way to add a story.

Per `docs/phase3-tasks-2026-04-28.md` Task 1.11 + §B2.1 of the strategy doc.
The agent never edits `stories/*.json` directly; it writes a bilingual spec
to `pipeline/inputs/story_N.bilingual.json` and runs this orchestrator. The
orchestrator runs the full deterministic gauntlet:

    1. agent_brief             — assemble the JSON context the agent should
                                  have consulted before writing the spec
    2. spec_exists             — fast preflight on the spec
    3. build                   — deterministic tokenization (text_to_story)
    4. validate                — full library validator (Checks 1–11,
                                  semantic_lint via Check 11)
    5. mint_budget             — caps new vocab per story (skill §C defaults)
    6. pedagogical_sanity      — every grammar point in `must_reinforce` debt
                                  MUST appear in this story
    7. vocab_reinforcement     — every word in the R1 must-reinforce list
                                  MUST appear in this story
    8. coverage_floor          — every post-bootstrap story must introduce
                                  ≥1 new grammar point until the current
                                  JLPT tier is fully covered
    9. write to stories/       — runs state_updater + regenerate_all_stories
                                  to mint W-IDs and refresh `is_new` flags
   10. audio rebuild           — per-sentence + per-word MP3s

ALL gauntlet steps are deterministic and HARD BLOCK per Phase 3 §0.1: a
failure does not ship the story.

This orchestrator does NOT contain a `step_literary_review` step. The
literary-review discipline that was originally specced as a Python LLM
gate (`pipeline/literary_review.py`) was retired 2026-04-29 in favour of
an in-skill discipline (SKILL §B.0 premise contract, §B.1 forbidden
zones via `pipeline/tools/forbid.py`, §E.5 prosecutor pass, §E.6 EN-only
re-read, §E.7 fresh-eyes subagent review, §G override budget). The
in-skill discipline runs BEFORE the live ship in author_loop, so the
discard cost is re-draft-only (not re-state). See SKILL.md for details.

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
        "だれ": "N5_dare_who", "誰":   "N5_dare_who",
        "どこ": "N5_doko_where",
        "いつ": "N5_itsu_when",
        "なぜ": "G053_naze_why",
    }
    COUNTER_SURFACES = {"一人", "二人", "三人", "四人", "五人", "ひとり", "ふたり"}
    ARU_IRU_BASES   = {"ある", "いる"}
    QUOTATIVE_VERBS = {
        "思います": "N4_to_omoimasu",
        "言います": "N4_to_iimasu",
    }

    for sent in built_story.get("sentences", []):
        toks = sent.get("tokens", [])
        # Pass A: surface/base-driven retags
        for tok in toks:
            t = tok.get("t", "")
            if t in NAN_SURFACES:
                tok["grammar_id"] = "N5_nan_what"
            elif t in KOSOADO_SURFACES and tok.get("role") == "content":
                tok["grammar_id"] = "N5_kosoado"
            elif t in INTERROGATIVE_GIDS:
                tok["grammar_id"] = INTERROGATIVE_GIDS[t]
            elif t in COUNTER_SURFACES and tok.get("role") == "content":
                tok["grammar_id"] = "N5_counters"
            elif tok.get("role") == "content":
                base = (tok.get("inflection") or {}).get("base")
                cur_gid = tok.get("grammar_id")
                if base in ARU_IRU_BASES and cur_gid in (None, "N5_masu_nonpast"):
                    tok["grammar_id"] = "N5_aru_iru"
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
        # Pass C: clause-conjunctive が ("but") — mirrors regenerate_all_stories.
        # Without this the gauntlet's coverage_floor undercounts N5_ga_but
        # at dry-run time, even though the post-ship regen WILL tag it. See
        # AGENTS.md "auto-tagged grammar IDs" section for the broader context.
        for j, tok in enumerate(toks):
            if tok.get("t") == "が" and tok.get("role") == "particle":
                prev = toks[j - 1] if j > 0 else None
                nxt  = toks[j + 1] if j + 1 < len(toks) else None
                if prev is not None and nxt is not None:
                    prev_t = prev.get("t", "")
                    is_predicate = (
                        prev_t in {"です", "だ", "ます", "せん"}
                        or prev_t.endswith("ます")
                        or prev_t.endswith("ません")
                        or prev_t.endswith("した")
                        or prev.get("role") == "aux"
                    )
                    if is_predicate:
                        tok["grammar_id"] = "N5_ga_but"


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
        # `regenerate_all_stories.regen_one` post-pass (e.g. N5_aru_iru,
        # N4_to_omoimasu, N4_to_iimasu, N5_kara_because, etc.). The
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

    Note (2026-04-29): the `must_reinforce` rule was relaxed in
    `agent_brief._vocab_reinforcement_debt` to flag a word ONLY when
    the R1 window is about to close on it (the LAST follow-up slot)
    AND the word was not minted during the bootstrap front-load. This
    step itself is unchanged; it just blocks fewer cases now because
    the brief flags fewer words. Words that are due-soon-but-not-yet-
    last-chance show up as `should_reinforce` warnings (non-blocking).
    The post-ship test `test_vocab_words_are_reinforced` (R1) is
    unchanged and remains the source of truth for what "reinforced"
    means.
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
    # The v2.5 reload (2026-04-29) replaced the "skip during bootstrap"
    # behavior with an explicit per-story grammar_min from the ladder.
    # Bootstrap stories now MUST hit their ladder-prescribed floor
    # (story 1: 6, story 2: 3, etc., tapering to 1 by story 9) — they
    # don't get a free pass anymore. Stories 11+ keep the legacy
    # "must_introduce when uncovered points remain" rule.
    try:
        from grammar_progression import ladder_for  # noqa: E402
        ladder = ladder_for(story_id)
        grammar_floor = ladder["grammar_min"]
    except Exception:
        ladder = {"grammar_min": 1, "in_bootstrap": False}
        grammar_floor = 1
    try:
        brief = agent_brief.build_brief(story_id)
        debt = brief.get("grammar_introduction_debt") or {}
        # Steady-state stories (no ladder row) keep the legacy
        # "skip if no must_introduce" behavior; bootstrap stories with
        # a positive grammar_min are evaluated against that floor
        # regardless of must_introduce.
        if not ladder.get("in_bootstrap") and not debt.get("must_introduce"):
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
                #      N5_dictionary_form, the first plain-form
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
                # Single grammar id namespace (since 2026-05-01): the gid
                # IS the catalog id. Fall back to the gid when the legacy
                # `catalog_id` join field is absent (steady-state case
                # after `pipeline/tools/rename_gids.py`).
                gid_to_cid = {
                    gid: e.get("catalog_id") or gid
                    for gid, e in (gstate.get("points") or {}).items()
                }
                # Registry entries take effect ONLY when the gid is not
                # already in state (state is the source of truth once
                # ship attribution has happened).
                for gid, defn in _AUTO_DEFS.items():
                    if gid not in gid_to_cid:
                        gid_to_cid[gid] = defn.get("catalog_id") or gid
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

        if len(story_intros) >= grammar_floor:
            return StepResult(
                "coverage_floor", "ok",
                f"Story introduces {len(story_intros)} new grammar point(s) "
                f"(ladder floor = {grammar_floor}): {sorted(story_intros)}.",
                details={"intros": sorted(story_intros),
                         "grammar_floor": grammar_floor,
                         "in_bootstrap": ladder.get("in_bootstrap")},
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
            f"Story {story_id} introduces {len(story_intros)} new grammar "
            f"point(s) but the ladder floor for this slot is {grammar_floor}. "
            f"Pick at least {grammar_floor - len(story_intros)} more from "
            f"`grammar_introduction_debt.recommended_for_this_story` "
            f"(the seed plan in `data/v2_5_seed_plan.json` lists the "
            f"prescribed picks for bootstrap slots).",
            details={
                "story_intros": sorted(story_intros),
                "grammar_floor": grammar_floor,
                "in_bootstrap": ladder.get("in_bootstrap"),
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
    # The v2.5 reload (2026-04-29) reads vocab caps from the bootstrap
    # ladder. Stories 1..BOOTSTRAP_END (= 10) get explicit per-story
    # (vocab_min, vocab_max) bounds; stories 11+ fall through to the
    # brief's `mint_budget` block (which still defaults to ~5).
    try:
        from grammar_progression import ladder_for  # noqa: E402
        ladder = ladder_for(story_id)
    except Exception:
        ladder = {"vocab_min": 0, "vocab_max": None, "in_bootstrap": False}
    try:
        brief = agent_brief.build_brief(story_id)
        budget = brief.get("mint_budget") or {}
        # Ladder cap (if any) takes precedence; brief is the fallback for
        # steady-state stories where vocab_max is None.
        cap = ladder.get("vocab_max")
        if cap is None:
            cap = int(budget.get("max", 9999))
        floor = ladder.get("vocab_min", int(budget.get("min", 0)))
        new_words = list((build_report or {}).get("new_words") or [])
        n_minted = len(new_words)
        if n_minted > cap:
            return StepResult(
                "mint_budget", "fail",
                f"Minted {n_minted} new word(s) but cap is {cap}"
                f"{' (ladder)' if ladder.get('in_bootstrap') else ''}. "
                f"Trim mints or document the expansion in the spec's "
                f"`intent` (and burn an override per SKILL §G).",
                details={
                    "minted": [w.get("id") for w in new_words],
                    "cap": cap, "floor": floor,
                    "in_bootstrap": ladder.get("in_bootstrap"),
                    "rationale": budget.get("rationale", ""),
                },
            )
        if n_minted < floor:
            return StepResult(
                "mint_budget", "fail",
                f"Minted {n_minted} new word(s) but floor is {floor}"
                f"{' (ladder)' if ladder.get('in_bootstrap') else ''}. "
                f"The bootstrap slot prescribes a wider seed than was "
                f"used; pull from `data/v2_5_seed_plan.json` for this "
                f"slot's must-mint set.",
                details={
                    "minted": [w.get("id") for w in new_words],
                    "cap": cap, "floor": floor,
                    "in_bootstrap": ladder.get("in_bootstrap"),
                },
            )
        return StepResult(
            "mint_budget", "ok",
            f"Minted {n_minted} new word(s); ladder window [{floor}, {cap}].",
            details={"minted": [w.get("id") for w in new_words],
                     "cap": cap, "floor": floor,
                     "in_bootstrap": ladder.get("in_bootstrap")},
        )
    except Exception as e:
        return StepResult(
            "mint_budget", "fail",
            f"mint_budget crashed: {e}",
            details=traceback.format_exc(),
        )


def step_vocab_difficulty(story_id: int, build_report: dict | None) -> StepResult:
    """HARD-BLOCK: are any newly-minted words above this story's tier cap?

    Per the lexical-difficulty cap added 2026-04-29 (and promoted from
    soft-warn to hard-block on 2026-04-29 evening after the corpus
    backfill), each story has a JLPT level + nf-band ceiling on what
    it may mint. This step inspects the newly-minted words from the
    build report and FAILS the gauntlet if any exceed the cap and are
    not explicitly absorbed by `lexical_overrides`.

    The spec MAY declare `lexical_overrides: ["surface", ...]` to
    consciously absorb above-cap mints (max
    MAX_OVERRIDES_PER_STORY=2). An override use is logged as
    informational `ok` (not warn), with details so the author sees the
    budget burn. Exceeding the override budget is a fail.
    """
    try:
        from lexical_difficulty import (  # noqa: E402
            tier_cap,
            difficulty_from_vocab_record,
            lookup_difficulty,
            evaluate_cap,
            MAX_OVERRIDES_PER_STORY,
        )
        from _paths import load_spec  # noqa: E402

        cap_jlpt, cap_nf = tier_cap(story_id)
        new_words = list((build_report or {}).get("new_words") or [])
        # Pull declared overrides from the spec.
        try:
            spec = load_spec(story_id) or {}
            overrides = list(spec.get("lexical_overrides") or [])
        except Exception:
            overrides = []
        flagged: list[dict] = []
        accepted_overrides: list[dict] = []
        for w in new_words:
            # Build report's "new_words" entries are the freshly-minted
            # vocab records — they should already carry jlpt/nf_band
            # from the mint enrichment, but lookup_difficulty handles
            # missing fields gracefully.
            diff = (
                difficulty_from_vocab_record(w)
                if any(k in w for k in ("jlpt", "nf_band", "common_tags"))
                else lookup_difficulty(w.get("surface", ""), w.get("kana", ""))
            )
            dec = evaluate_cap(diff, story_id)
            if dec.above_cap:
                surface = w.get("surface", "")
                bucket = (
                    accepted_overrides if surface in overrides else flagged
                )
                bucket.append({
                    "id": w.get("id"),
                    "surface": surface,
                    "kana": w.get("kana", ""),
                    "jlpt": diff.jlpt,
                    "nf_band": diff.nf_band,
                    "reason": dec.reason,
                })
        # Even when all flagged words are absorbed by overrides, we
        # surface a warning so the author sees the override budget burn.
        if len(accepted_overrides) > MAX_OVERRIDES_PER_STORY:
            return StepResult(
                "vocab_difficulty", "fail",
                f"Story {story_id} accepts {len(accepted_overrides)} "
                f"lexical overrides but the per-story max is "
                f"{MAX_OVERRIDES_PER_STORY}. Trim mints or split the "
                f"scene across stories.",
                details={
                    "cap_jlpt": cap_jlpt, "cap_nf": cap_nf,
                    "accepted_overrides": accepted_overrides,
                    "flagged": flagged,
                    "policy": "hard-block (since 2026-04-29 evening)",
                },
            )
        if flagged:
            return StepResult(
                "vocab_difficulty", "fail",
                f"Story {story_id} mints {len(flagged)} above-cap "
                f"word(s) without `lexical_overrides`: "
                f"{', '.join(w['surface'] for w in flagged)}. "
                f"Cap is N{cap_jlpt}/nf{cap_nf:02d}. "
                f"Either rewrite to use a more common word, or add to "
                f"spec.lexical_overrides if genuinely load-bearing.",
                details={
                    "cap_jlpt": cap_jlpt, "cap_nf": cap_nf,
                    "flagged": flagged,
                    "accepted_overrides": accepted_overrides,
                    "policy": "hard-block (since 2026-04-29 evening)",
                },
            )
        if accepted_overrides:
            return StepResult(
                "vocab_difficulty", "ok",
                f"Story {story_id}: {len(accepted_overrides)} lexical "
                f"override(s) accepted; {len(new_words)} mints overall.",
                details={
                    "cap_jlpt": cap_jlpt, "cap_nf": cap_nf,
                    "accepted_overrides": accepted_overrides,
                },
            )
        return StepResult(
            "vocab_difficulty", "ok",
            f"All {len(new_words)} new mint(s) at or below "
            f"N{cap_jlpt}/nf{cap_nf:02d} cap.",
            details={"cap_jlpt": cap_jlpt, "cap_nf": cap_nf},
        )
    except Exception as e:
        return StepResult(
            "vocab_difficulty", "warn",
            f"vocab_difficulty crashed (non-blocking): {e}",
            details=traceback.format_exc(),
        )


## Retired 2026-04-29: step_literary_review.
##
## Originally a stub awaiting `pipeline/literary_review.py` (Task 1.10).
## The whole gate has been moved out of the pipeline and into the
## monogatari-author skill, where it sits BEFORE the live ship as
## §B.0 (premise contract), §B.1 (forbidden zones via
## pipeline/tools/forbid.py), §E.5 (prosecutor pass), §E.6 (EN-only
## re-read), §E.7 (fresh-eyes subagent review), and §G (override
## budget). A Python LLM call would have used the same model family as
## the author with a worse prompt; the in-skill discipline avoids
## that, runs cheaper, and avoids the sunk-cost problem (because it
## happens BEFORE state mutations, not after).
##
## Do NOT add a step_literary_review back to this file. Adding one
## just re-introduces the failure mode where a stub silently returns
## "skipped" and gives every reader the impression that quality has
## been gated when it has not been. If the in-skill discipline ever
## proves insufficient, build a NEW step with a clearly different
## name (e.g. `step_corpus_diversity_lint`) and a real, non-stub
## implementation.


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

        # ── Post-condition guard (added 2026-04-29 after the v2.5
        # reload shipped story 1 with absolute audio paths to prod).
        # The audio_builder's _rel_for_json helper should make this
        # impossible to construct, but a defense-in-depth check here
        # surfaces any regression at the gauntlet level instead of at
        # `pytest pipeline/tests/` time. Cheap; runs once per ship.
        try:
            shipped = json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            shipped = {}
        absolute_paths: list[str] = []
        for sent in shipped.get("sentences", []):
            ap = sent.get("audio")
            if ap and (ap.startswith("/") or ap.startswith("\\")):
                absolute_paths.append(f"sentence {sent.get('idx')}: {ap}")
        for wid, ap in (shipped.get("word_audio") or {}).items():
            if ap and (ap.startswith("/") or ap.startswith("\\")):
                absolute_paths.append(f"word_audio[{wid}]: {ap}")
        if absolute_paths:
            return StepResult(
                "audio", "fail",
                f"Audio built BUT story JSON contains absolute paths "
                f"that will 404 on prod. This means audio_builder's "
                f"path-rewriting policy regressed. Fix "
                f"`_rel_for_json` in pipeline/audio_builder.py.\n  "
                + "\n  ".join(absolute_paths),
                details={"absolute_paths": absolute_paths},
            )

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
    (e.g. N5_dictionary_form on the first plain-form verb usage)
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
    # Content-class mints (count toward mint budget).
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

    # Function-class mints (conjunctions like だから, でも, そして). These do
    # NOT count toward mint budget (they're functional, not content-class)
    # but DO need to be persisted as vocab so the reading-app's lookup
    # popups can resolve them. They flow through the same
    # state_updater.new_word_definitions channel — state_updater treats
    # them identically to content vocab for state writeback.
    for rec in build_report.get("new_function_words", []) or []:
        wid = rec.get("id")
        if not wid:
            continue
        plan["new_word_definitions"][wid] = {
            "surface":  rec.get("surface", wid),
            "kana":     rec.get("kana", ""),
            "reading":  rec.get("reading", ""),
            "pos":      rec.get("pos", "conjunction"),
            "meanings": list(rec.get("meanings") or []),
        }

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

    # --- Backup hygiene (auto-prune old state_backups) -----------------
    #
    # Each ship writes a fresh backup to `state_backups/{vocab,grammar}_state_*.json`
    # plus N more under `state_backups/regenerate_all_stories/`. Without
    # pruning, the directory grows ~3-10 files per ship and 19MB had
    # accumulated by 2026-05-01 — half of which were also tracked in
    # git history (.gitignore exempted only sub-directories).
    #
    # Policy: keep last 5 backups per stem, and anything <1 day old.
    # Honest tradeoff: 5 backups is enough for "undo my last attempt or
    # two"; recovery from older states should come from git, not from
    # state_backups/.
    try:
        import subprocess as _subprocess
        for _subdir in ("", "regenerate_all_stories"):
            _args = [
                "python3", "pipeline/tools/cleanup_state_backups.py",
                "--keep", "5", "--days", "1", "--apply",
            ]
            if _subdir:
                _args.extend(["--subdir", _subdir])
            _subprocess.run(_args, check=False, capture_output=True, cwd=ROOT)
    except Exception:
        # Cleanup is hygiene, not correctness — never let it break a ship.
        pass

    # --- Reconciliation no longer needed (Phase A derive-on-read) ------
    #
    # Pre-2026-05-01, this block called `reconcile_grammar_intros` to
    # repair `intro_in_story` drift on `data/grammar_state.json`. After
    # Phase A, that field is no longer stored — it is derived from the
    # corpus by `derived_state.derive_grammar_attributions()` and
    # projected for the reader by `regenerate_all_stories.py --apply`'s
    # `build_grammar_attributions.write_attributions()` call. There is
    # nothing to reconcile because there is no longer any cached value
    # that could disagree with the corpus.
    #
    # Pinned by:
    #   * test_grammar_state_carries_no_attribution_fields
    #   * test_grammar_attribution_manifest_in_sync_with_corpus

    return StepResult(
        "write", "ok",
        f"Wrote {sp.name}, updated vocab/grammar state "
        f"({len(summary.get('words_added') or [])} new word(s), "
        f"{len(summary.get('grammar_added') or [])} new grammar point(s)), "
        f"and refreshed is_new flags + grammar attribution projection.",
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

    # Step 5.55: vocab difficulty (HARD BLOCK since 2026-04-29 evening).
    # See step_vocab_difficulty docstring for the override discipline.
    s_vdiff = step_vocab_difficulty(story_id, report)
    steps.append(s_vdiff)
    if s_vdiff.status == "fail":
        return _make_verdict(story_id, steps, dry_run, halted_at="vocab_difficulty")

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

    # Step 6 (RETIRED 2026-04-29): literary review used to live here as
    # `step_literary_review`. The gate now lives in the monogatari-author
    # skill (§B.0 / §B.1 / §E.5 / §E.6 / §E.7 / §G) and runs BEFORE the
    # live `author_loop.py author N` invocation. Do not re-add a Python
    # gate here — see the tombstone comment near step_audio for why.

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
    # NOTE: the `reviewer_escalated` / exit-code-3 branch was retired with
    # step_literary_review on 2026-04-29. The verdict is now binary:
    # "fail" (any blocking step failed) or "ship"/"would_ship" otherwise.
    # The literary-review discipline lives in the skill and is a separate
    # human-visible step — see SKILL §E.5–E.7.
    if blocking_failures:
        verdict = "fail"
        exit_code = 1
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
