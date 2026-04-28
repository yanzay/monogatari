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
        plan: dict | None = None
        if build_report:
            minted_word_ids = [w["id"] for w in (build_report.get("new_words") or [])]
            minted_grammar  = list(build_report.get("new_grammar") or [])
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


def step_audio(story_id: int) -> StepResult:
    """STUB until wired to pipeline/audio_builder."""
    return StepResult(
        "audio", "skipped",
        "Stub: audio rebuild is not yet wired (Phase 3a future task). "
        "Run pipeline/audio_builder.py manually if voice files are needed.",
        blocking=False,
    )


def step_write(story_id: int, built_story: dict, dry_run: bool) -> StepResult:
    if dry_run:
        return StepResult(
            "write", "skipped",
            f"--dry-run: would have written {story_path(story_id).name}.",
            blocking=False,
        )
    try:
        sp = story_path(story_id)
        write_json(sp, built_story)
        return StepResult("write", "ok", f"Wrote {sp.name}.")
    except Exception as e:
        return StepResult("write", "fail",
                          f"Could not write story file: {e}",
                          details=traceback.format_exc())


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

    # Step 6: literary review (non-blocking)
    s_rev = step_literary_review(built)
    steps.append(s_rev)

    # Step 7: write
    s_write = step_write(story_id, built, dry_run)
    steps.append(s_write)
    if s_write.status == "fail":
        return _make_verdict(story_id, steps, dry_run, halted_at="write")

    # Step 8: audio
    steps.append(step_audio(story_id))

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
                   help="just emit agent_brief JSON for this story id and exit")
    a.add_argument("--json", action="store_true",
                   help="emit verdict as JSON instead of human format")
    args = p.parse_args()

    story_id = parse_story_id(args.story)

    if args.brief_only:
        brief = agent_brief.build_brief(story_id)
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
